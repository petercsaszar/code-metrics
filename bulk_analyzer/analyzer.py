import os
import re
import json
import subprocess
import shutil
import git
import yaml
import requests
try:
    from .milestone_commit_finder import get_milestone_commits
    from .dotnet_environment import ensure_dotnet_environment
except ImportError:
    from milestone_commit_finder import get_milestone_commits
    from dotnet_environment import ensure_dotnet_environment
import logging
import argparse

# Configure logging
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_FILE = os.getenv("ANALYSIS_LOGFILE", os.path.join(WORKSPACE, "analysis_errors.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Root logger configuration: console + file handler for errors
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

# Console handler
ch = logging.StreamHandler()
ch.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
ch.setFormatter(formatter)
root_logger.addHandler(ch)

try:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)
except Exception as e:
    root_logger.warning("Could not create log file %s: %s", LOG_FILE, e)

# === Load Configuration ===
CONFIG_PATH = os.getenv("ANALYZER_CONFIG", os.getenv("CONFIG_PATH", "config.yml"))

with open(CONFIG_PATH, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

GITLAB_URL = config["gitlab"]["url"]
TOKEN = config["gitlab"]["token"]
BUMPY_ANALYZER_PATH = config.get("bumpy_analyzer_path", "./BumpyRoadAnalyzer")
MILESTONES = config["gitlab"]["milestone_keywords"]
CLONE_DIR = config["project"]["clone_dir"]

ANALYZER_DIR = config["analyzer"]["project_dir"]
MSBUILD_DIR = config["analyzer"]["msbuild_dir"]
ANALYZER_PROJECT_FILE = config["analyzer"]["project_file"]
UNITY_PATH = config["analyzer"]["unity_path"]
UNITY_VERSION = config["analyzer"]["unity_version"]
CLOC_BINARY = config["analyzer"].get("cloc_path", "cloc")

HEADERS = {"PRIVATE-TOKEN": TOKEN}
# Globals for CLI-driven persisted state (can be overridden from __main__)
REPORT_OUTPUT = os.getenv("REPORT_OUTPUT", "analysis_results.json")
PROCESSED_COMMITS_PATH = os.getenv("PROCESSED_COMMITS_PATH", "processed_commits.json")
FORCE_REANALYZE = False


def _calculate_lines_of_code_fallback(repo_path, extensions=(".cs",), exclude_dirs=None):
    """Fallback LOC calculation: count non-empty lines in matching source files."""
    if exclude_dirs is None:
        exclude_dirs = {
            ".git",
            ".vs",
            "bin",
            "obj",
            "Library",
            "Packages",
            "Temp",
            "Logs",
            "UserSettings",
            "node_modules",
        }

    loc = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if not file.endswith(extensions):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:    
                    for line in source_file:
                        if line.strip():
                            loc += 1
            except OSError as e:
                logging.warning("Could not read file for LOC count: %s (%s)", file_path, e)

    return loc


def calculate_lines_of_code(repo_path, extensions=(".cs",), exclude_dirs=None):
    """Calculate LOC using cloc when available; otherwise use fallback counting."""
    if exclude_dirs is None:
        exclude_dirs = {
            ".git",
            ".vs",
            "bin",
            "obj",
            "Library",
            "Packages",
            "Temp",
            "Logs",
            "UserSettings",
            "node_modules",
        }

    cloc_binary = os.getenv("CLOC_PATH", CLOC_BINARY)
    cloc_available = shutil.which(cloc_binary) is not None

    if cloc_available:
        include_lang = "C#" if ".cs" in extensions else None
        exclude_dir_arg = ",".join(sorted(exclude_dirs))

        cloc_command = [
            cloc_binary,
            "--json",
            "--quiet",
            "--exclude-dir",
            exclude_dir_arg,
        ]

        if include_lang:
            cloc_command += ["--include-lang", include_lang]

        cloc_command.append(repo_path)

        try:
            result = subprocess.run(
                cloc_command,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0 and result.stdout:
                cloc_output = json.loads(result.stdout)
                if "SUM" in cloc_output and "code" in cloc_output["SUM"]:
                    return int(cloc_output["SUM"]["code"])

            logging.warning(
                "cloc failed for %s (exit=%s), falling back to internal LOC count. stderr=%s",
                repo_path,
                result.returncode,
                result.stderr.strip(),
            )
        except Exception as e:
            logging.warning("cloc execution failed for %s, fallback LOC will be used: %s", repo_path, e)

    return _calculate_lines_of_code_fallback(repo_path, extensions=extensions, exclude_dirs=exclude_dirs)

def get_project_info(project_id):
    """Fetch project information from GitLab to get the correct HTTP URL."""
    url = f"{GITLAB_URL}/projects/{project_id}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        project_data = response.json()
        return project_data["http_url_to_repo"]  # Return the HTTP URL for cloning
    else:
        print(f"❌ Failed to fetch project {project_id} info: {response.text}")
        return None


def clone_repo(project_id):
    """Clone the GitLab repository if not cloned yet, using the correct URL."""
    repo_path = os.path.join(CLONE_DIR, str(project_id))

    repo_url = get_project_info(project_id)  # Get the correct repository URL
    if not repo_url:
        print(f"⚠ Skipping project {project_id} - Repository URL not found")
        return None

    # add auth token
    repo_url = repo_url.replace("https://", f"https://oauth2:{TOKEN}@")

    if not os.path.exists(repo_path):
        print(f"🔄 Cloning repository {project_id} from {repo_url} ...")
        os.makedirs(CLONE_DIR, exist_ok=True)
        git.Repo.clone_from(repo_url, repo_path)
    else:
        print(f"✅ Repository {project_id} already exists.")
        # repo = git.Repo(repo_path)
        # repo.remotes.origin.pull()

    return repo_path



def checkout_commit(repo_path, commit_id):
    """Checkout the specific commit."""
    repo = git.Repo(repo_path)
    repo.git.checkout(commit_id, force=True)
    
    try:
        subprocess.run(["git", "clean", "-xdf"], cwd=repo_path, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to achieve wipe on git repository: {e.stderr or e.stdout}")

    print(f"Checked out commit {commit_id}")

def run_analyzers(repo_path, solution_path=None, custom_build_command=None):
    """Run the roslyn analyzers."""
    project_path = os.path.join(ANALYZER_DIR, ANALYZER_PROJECT_FILE)
    if not solution_path:
        solution_path = find_solution_file(repo_path)
    else:
        solution_path = os.path.join(repo_path, solution_path)
    if not solution_path:
        print("❌ No solution found.")
        return None

    print(f"🚀 Running analyzers for {repo_path} ...")
    logging.info("Running analyzers for %s", repo_path)

    try:
        build_solution(repo_path, solution_path, custom_build_command)
    except subprocess.CalledProcessError as e:
        logging.warning("Build error, trying analyzers anyway: %s", e)

    # Prefer running from the project file if available; otherwise try the bundled published dll in the image
    if os.path.exists(project_path):
        analyze_command = [
            "dotnet", "run", "--project", project_path, "analyze", solution_path
        ]
    else:
        # Look for a bundled analyzer published to a known location inside the container
        bundled_dir = os.getenv("BUNDLED_ANALYZER_PATH", "/opt/CodeMetricsAnalyzer")
        dll_path = os.path.join(bundled_dir, "CodeMetricsAnalyzer.dll")
        if os.path.exists(dll_path):
            analyze_command = ["dotnet", dll_path, "analyze", solution_path]
        else:
            # Fallback: try to run using the analyzer dir in case image mounted differently
            analyze_command = [
                "dotnet", "run", "--project", project_path, "analyze", solution_path
            ]
    if MSBUILD_DIR and os.path.isdir(MSBUILD_DIR):
        analyze_command += ["--msbuild-path", MSBUILD_DIR]

    logging.info("Executing analyzer command: %s", " ".join(analyze_command))
    result = subprocess.run(analyze_command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
    logging.debug("Analyzer exit=%s stdout=\n%s\nstderr=\n%s", result.returncode, result.stdout, result.stderr)

    if result.returncode != 0:
        logging.error("Analyzer failed (exit %s). Command: %s", result.returncode, " ".join(analyze_command))
        logging.error("stdout:\n%s", result.stdout)
        logging.error("stderr:\n%s", result.stderr)
        return None

    match_bumpy = re.search(r"(\d+)\s+CMA0001", result.stdout)
    match_fpc = re.search(r"(\d+)\s+CMA0002", result.stdout)
    match_lcom5 = re.search(r"(\d+)\s+CMA0004", result.stdout)
    match_lcom4 = re.search(r"(\d+)\s+CMA0003", result.stdout)
    match_maintainability_index = re.search(r"(\d+)\s+CMA0005", result.stdout)
    match_cyclomatic_complexity = re.search(r"(\d+)\s+CMA0006", result.stdout)
    match_class_coupling = re.search(r"(\d+)\s+CMA0007", result.stdout)

    lines_of_code = calculate_lines_of_code(repo_path)

    bumpy_score = int(match_bumpy.group(1)) if match_bumpy else 0
    fpc_score = int(match_fpc.group(1)) if match_fpc else 0
    lcom5_score = int(match_lcom5.group(1)) if match_lcom5 else 0
    lcom4_score = int(match_lcom4.group(1)) if match_lcom4 else 0
    maintainability_index_score = int(match_maintainability_index.group(1)) if match_maintainability_index else 0
    cyclomatic_complexity_score = int(match_cyclomatic_complexity.group(1)) if match_cyclomatic_complexity else 0
    class_coupling_score = int(match_class_coupling.group(1)) if match_class_coupling else 0

    formatted_result = {
        "bumpy_score": bumpy_score,
        "fpc_score": fpc_score,
        "lcom4_score": lcom4_score,
        "lcom5_score": lcom5_score,
        "maintainability_index_score": maintainability_index_score,
        "cyclomatic_complexity_score": cyclomatic_complexity_score,
        "class_coupling_score": class_coupling_score,
        "lines_of_code": lines_of_code,
    }

    return formatted_result

def build_solution(repo_path, solution_path, custom_build_command=None):
    ensure_dotnet_environment(repo_path)
    clean_command = [
            "dotnet", "clean", solution_path
        ]
    subprocess.run(clean_command, capture_output=True, text=True, check=False)

    if (custom_build_command is None):
        build_command = [
        "dotnet", "build", solution_path
        ]
        subprocess.run(build_command, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
    else:
        build_command = f"cd {repo_path} && {custom_build_command}"
        subprocess.run(build_command, capture_output=True, text=True, check=True, shell=True, encoding="utf-8", errors="replace")

    subprocess.run(clean_command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")

def analyze_milestone(milestone_keywords = None):
    """Analyze all milestone commits using Bumpy Road Analyzer."""
    print(f"🔍 Fetching commits for milestone: {milestone_keywords}")
    # try:
    #      with open("commit_data.json", "r") as file:
    #         commit_data = json.load(file)
    # except (FileNotFoundError):
    #     get_milestone_commits(milestone_keywords)
    #     with open("commit_data.json", "r") as file:
    #         commit_data = json.load(file)
    commit_data = get_milestone_commits(milestone_keywords)

    # load processed commits state
    try:
        with open(PROCESSED_COMMITS_PATH, "r", encoding="utf-8") as pf:
            processed_commits = json.load(pf)
    except Exception:
        processed_commits = {}

    results = {}

    for project_id, project_data in commit_data.items():
        try:
            repo_path = clone_repo(project_id)
            commit_id = project_data.get("last_commit_id")

            if not commit_id or not repo_path:
                continue

            # skip if we've already processed this commit for this project
            processed_for_project = processed_commits.get(str(project_id), [])
            if (commit_id in processed_for_project) and (not FORCE_REANALYZE):
                logging.info("Skipping already processed project %s @ %s", project_id, commit_id)
                continue

            checkout_commit(repo_path, commit_id)
            analysis_result = run_analyzers(repo_path)

            if analysis_result:
                lines_of_code = calculate_lines_of_code(repo_path)
                results[project_id] = {
                    "project_id": project_id,
                    "commit_id": commit_id,
                    "bumpy_score": analysis_result["bumpy_score"],
                    "fpc_score": analysis_result["fpc_score"],
                    "lcom5_score": analysis_result["lcom5_score"],
                    "lcom4_score": analysis_result["lcom4_score"],
                    "maintainability_index_score": analysis_result["maintainability_index_score"],
                    "cyclomatic_complexity_score": analysis_result["cyclomatic_complexity_score"],
                    "class_coupling_score": analysis_result["class_coupling_score"],
                    "lines_of_code": lines_of_code,
                }
                logging.info("LOC calculated for project %s at %s: %s", project_id, commit_id, lines_of_code)

                # persist processed commit immediately
                processed_for_project = processed_commits.setdefault(str(project_id), [])
                if commit_id not in processed_for_project:
                    processed_for_project.append(commit_id)
                    try:
                        with open(PROCESSED_COMMITS_PATH, "w", encoding="utf-8") as pf:
                            json.dump(processed_commits, pf, indent=2)
                    except Exception as e:
                        logging.warning("Could not persist processed commits to %s: %s", PROCESSED_COMMITS_PATH, e)
        except Exception as e:
            print(f"❌ Error analyzing project {project_id}: {e}")


    return results

def analyze_all_milestones():
    """Analyze all milestone commits dynamically."""
    # Decide on output directory. REPORT_OUTPUT may be a file path or directory.
    out_path = REPORT_OUTPUT
    out_dir = out_path if os.path.isdir(out_path) else os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    per_milestone_files = []
    ind = 1
    for milestone in MILESTONES:
        milestone_results = analyze_milestone(milestone)
        fname = os.path.join(out_dir, f"analysis_results_{ind}.json")
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(milestone_results or {}, f, indent=2)
            per_milestone_files.append(fname)
            print(f"Saved milestone results to {fname}")
        except Exception as e:
            logging.warning("Could not write milestone results to %s: %s", fname, e)
        ind += 1

    # Generate per-project HTML reports by filtering per-milestone JSONs
    try:
        from bulk_analyzer import html_report_generator as hrg  # type: ignore
        html_available = True
    except Exception:
        html_available = False

    # Collect all project ids seen across milestone files
    all_projects = set()
    for mf in per_milestone_files:
        try:
            with open(mf, "r", encoding="utf-8") as fh:
                payload = json.load(fh) or {}
            for k in payload.keys():
                all_projects.add(str(k))
        except Exception:
            continue

    if not per_milestone_files:
        print("No milestone result files produced; nothing to report.")
        return

    tmp_base = os.path.join(out_dir, "_tmp_inputs")
    os.makedirs(tmp_base, exist_ok=True)

    for project_id in sorted(all_projects):
        # create per-project input files
        project_inputs = []
        for idx, mf in enumerate(per_milestone_files, start=1):
            try:
                with open(mf, "r", encoding="utf-8") as fh:
                    payload = json.load(fh) or {}
                if project_id in payload:
                    single = {project_id: payload[project_id]}
                    tmpf = os.path.join(tmp_base, f"proj_{project_id}_m{idx}.json")
                    with open(tmpf, "w", encoding="utf-8") as tf:
                        json.dump(single, tf, indent=2)
                    project_inputs.append(tmpf)
            except Exception:
                continue

        if not project_inputs:
            continue

        # generate HTML using the module if available; otherwise call module as script
        out_html = os.path.join(out_dir, f"project_{project_id}_milestones.html")
        if html_available:
            try:
                hrg_main = getattr(hrg, "parse_args", None)
            except Exception:
                hrg_main = None
        # prefer subprocess call for isolation
        try:
            cmd = [sys.executable, "-m", "bulk_analyzer.html_report_generator", "--output", out_html, "--inputs"] + project_inputs
            subprocess.run(cmd, check=True)
            print(f"Generated HTML report for project {project_id}: {out_html}")
        except Exception as e:
            logging.warning("Failed to generate HTML for project %s: %s", project_id, e)

    # cleanup temporary inputs
    try:
        shutil.rmtree(tmp_base, ignore_errors=True)
    except Exception:
        pass

def find_solution_file(repo_path):
    """Recursively searches for a .sln file in the given repository directory."""
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".sln") or file.endswith(".slnx"):
                return os.path.join(root, file)
            
    # Check if it's a Unity project
    unity_project_settings = os.path.join(repo_path, "ProjectSettings", "ProjectVersion.txt")
    if os.path.exists(unity_project_settings):
        if (not UNITY_PATH):
            print("🎮 Detected Unity project. Unity is not configured, skipping...")
            return None
        print("🎮 Detected Unity project. Generating solution file...")
        generate_unity_solution(repo_path)
        
        # Search again for the generated solution
        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.endswith(".sln"):
                    return os.path.join(root, file)
    
    return None  # No solution file found

def generate_unity_solution(repo_path):
    """Uses Unity to generate a Visual Studio solution."""
    update_unity_project_version(repo_path)
    command = [
        UNITY_PATH, "-batchmode", "-quit", "-nographics", "-projectPath", repo_path, "-executeMethod", "UnityEditor.SyncVS.SyncSolution"
    ]
    try:
        subprocess.run(command, check=True)
        print("✅ Unity solution file generated.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating Unity solution: {e}")

def update_unity_project_version(project_path):
    version_file = os.path.join(project_path, "ProjectSettings", "ProjectVersion.txt")

    if not os.path.isfile(version_file):
        print(f"[ERROR] Couldn't find ProjectVersion.txt at: {version_file}")
        return

    lines = []
    found = False

    with open(version_file, "r") as f:
        for line in f:
            if line.startswith("m_EditorVersion:"):
                lines.append(f"m_EditorVersion: {UNITY_VERSION}\n")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"m_EditorVersion: {UNITY_VERSION}\n")

    with open(version_file, "w") as f:
        f.writelines(lines)

    print(f"[OK] Updated Unity version to {UNITY_VERSION}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Bulk analyzer runner")
    parser.add_argument("--report-output", help="Path to write combined analysis JSON", default=None)
    parser.add_argument("--processed-commits-file", help="Path to persist processed commits state", default=None)
    parser.add_argument("--force", action="store_true", help="Force reanalysis even if commit was processed before")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.report_output:
        REPORT_OUTPUT = args.report_output
    if args.processed_commits_file:
        PROCESSED_COMMITS_PATH = args.processed_commits_file
    if args.force:
        FORCE_REANALYZE = True

    analyze_all_milestones()
