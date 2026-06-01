import os
import re
import json
import subprocess
import shutil
import uuid
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

def run_analyzers(repo_path, solution_path=None, custom_build_command=None,
                  report_output=None, history_dir=None):
    """Run the roslyn analyzers.

    When *report_output* is provided the .NET HtmlReportGenerator is invoked
    (--report-output flag) to produce an incremental multi-page HTML report.
    *history_dir* overrides where historical XML snapshots are stored; it
    defaults to <report_output>/history when not given.
    """
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

    # If this repository contains a Unity project and the operator requested
    # building with the Unity editor, attempt a Unity CLI build (license
    # activation is handled if UNITY_LICENSE_PATH is provided).
    try:
        unity_root = _find_unity_project_root(repo_path)
        if unity_root:
            _run_unity_cli_build(repo_path, unity_root)
    except Exception as e:
        logging.warning("Unity build step failed: %s", e)

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

    if report_output:
        os.makedirs(report_output, exist_ok=True)
        analyze_command += ["--report-output", report_output]
        effective_history_dir = history_dir or os.path.join(report_output, "history")
        analyze_command += ["--history-dir", effective_history_dir]
        logging.info("HTML report will be written to: %s", report_output)

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
            "dotnet", "build", solution_path,
            "-p:EnableWindowsTargeting=true",
        ]
        subprocess.run(build_command, check=True, encoding="utf-8", errors="replace")
    else:
        build_command = f"cd {repo_path} && {custom_build_command}"
        subprocess.run(build_command, check=True, shell=True, encoding="utf-8", errors="replace")

    subprocess.run(clean_command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")

def analyze_milestone(milestone_keywords=None, report_output_base=None):
    """Analyze all milestone commits using Bumpy Road Analyzer.

    When *report_output_base* is provided each project's HTML report is
    generated (or updated) incrementally at
    <report_output_base>/project_<project_id>/ using the .NET
    HtmlReportGenerator.  Running this for successive milestones appends a
    new history entry each time so the final report shows a trend across all
    milestone commits.
    """
    print(f"🔍 Fetching commits for milestone: {milestone_keywords}")
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

            # Derive per-project HTML report directory when a base is provided.
            # Each milestone run appends a history entry so the report accumulates
            # across all milestones automatically.
            project_report_dir = (
                os.path.join(report_output_base, f"project_{project_id}")
                if report_output_base else None
            )

            analysis_result = run_analyzers(repo_path, report_output=project_report_dir)

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
    """Analyze all milestone commits dynamically.

    For each milestone, per-project JSON results are saved and the .NET
    HtmlReportGenerator is invoked with --report-output so that each project
    accumulates a history entry per milestone commit.  After all milestones
    have run, every project directory under <out_dir>/project_<id>/ contains
    a self-contained multi-page HTML report (index.html, summary.html,
    history.html, project_*.html) whose history page shows the trend across
    all milestone commits.
    """
    # Decide on output directory. REPORT_OUTPUT may be a file path or directory.
    out_path = REPORT_OUTPUT
    out_dir = out_path if os.path.isdir(out_path) else os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    per_milestone_files = []
    ind = 1
    for milestone in MILESTONES:
        milestone_results = analyze_milestone(milestone, report_output_base=out_dir)
        fname = os.path.join(out_dir, f"analysis_results_{ind}.json")
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(milestone_results or {}, f, indent=2)
            per_milestone_files.append(fname)
            print(f"Saved milestone results to {fname}")
        except Exception as e:
            logging.warning("Could not write milestone results to %s: %s", fname, e)
        ind += 1

    if not per_milestone_files:
        print("No milestone result files produced; nothing to report.")
        return

    # Summarise where reports were written
    seen_projects = set()
    for mf in per_milestone_files:
        try:
            with open(mf, "r", encoding="utf-8") as fh:
                payload = json.load(fh) or {}
            seen_projects.update(str(k) for k in payload)
        except Exception:
            continue

    for project_id in sorted(seen_projects):
        report_dir = os.path.join(out_dir, f"project_{project_id}")
        index_html = os.path.join(report_dir, "index.html")
        if os.path.isfile(index_html):
            print(f"📄 HTML report for project {project_id}: {index_html}")
        else:
            logging.warning("Expected HTML report not found for project %s at %s", project_id, report_dir)

def _find_unity_project_root(repo_path):
    """Walk repo_path looking for ProjectSettings/ProjectVersion.txt at any depth.

    Returns the directory that contains ProjectSettings/, or None if not found.
    The Unity project may live in a subdirectory (e.g. TransportTycoon/) rather
    than at the repo root, so a single os.path.exists check on the root is not
    sufficient.
    """
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in (".git", "Library", "Temp", "Logs")]
        if os.path.basename(root) == "ProjectSettings" and "ProjectVersion.txt" in files:
            return os.path.dirname(root)
    return None


def find_solution_file(repo_path):
    """Recursively searches for a .sln file in the given repository directory."""
    # Unity projects often commit a .slnx/.sln that references editor-generated
    # .csproj files which are not in the repo. Always use the generated solution
    # for Unity projects so the build doesn't fail with MSB3202.
    # Search recursively because the Unity project may live in a subdirectory.
    unity_project_root = _find_unity_project_root(repo_path)
    if unity_project_root:
        print("🎮 Detected Unity project.")
        # If possible, prefer to ask the Unity editor to sync the solution so
        # the .sln matches what Unity would generate. This is enabled when the
        # operator sets UNITY_SYNC_WITH_EDITOR or UNITY_BUILD_WITH_EDITOR.
        try:
            use_editor_sync = bool(os.environ.get("UNITY_SYNC_WITH_EDITOR") or os.environ.get("UNITY_BUILD_WITH_EDITOR"))
            unity_exec = _find_unity_executable()
            if use_editor_sync and unity_exec:
                logging.info("Attempting to sync Unity solution via editor: %s", unity_exec)
                # Activate license first if provided
                license_path = os.environ.get("UNITY_LICENSE_PATH")
                if license_path and os.path.isfile(license_path):
                    try:
                        act_cmd = [unity_exec, "-batchmode", "-nographics", "-manualLicenseFile", license_path, "-quit"]
                        logging.info("Activating Unity license before sync: %s", " ".join(act_cmd))
                        subprocess.run(act_cmd, check=True, cwd=unity_project_root)
                    except subprocess.CalledProcessError as e:
                        logging.warning("Unity license activation failed: %s", e)

                sync_cmd = [
                    unity_exec,
                    "-batchmode",
                    "-nographics",
                    "-projectPath",
                    unity_project_root,
                    "-executeMethod",
                    "UnityEditor.SyncVS.SyncSolution",
                    "-logFile",
                    "-",
                    "-quit",
                ]
                try:
                    res = subprocess.run(sync_cmd, check=False, capture_output=True, text=True, cwd=unity_project_root)
                    logging.debug("Unity sync stdout:\n%s", res.stdout)
                    logging.debug("Unity sync stderr:\n%s", res.stderr)
                    if res.returncode == 0:
                        # Unity writes the .sln into the project root — search for it now
                        for root, _, files in os.walk(unity_project_root):
                            for f in files:
                                if f.endswith('.sln') or f.endswith('.slnx'):
                                    sln_file = os.path.join(root, f)
                                    logging.info("Unity editor sync produced solution: %s", sln_file)
                                    return sln_file
                    else:
                        logging.warning("Unity editor sync returned %s; falling back to Python generator", res.returncode)
                except Exception as e:
                    logging.warning("Unity editor sync failed: %s; falling back to Python generator", e)
        except Exception as e:
            logging.warning("Unity sync attempt encountered error: %s", e)

        # Fall back to the pure-Python solution generator if editor sync was
        # not requested, not available, or failed.
        print("Generating solution file using pure-Python generator...")
        sln_path = generate_unity_solution(unity_project_root)
        if sln_path and os.path.isfile(sln_path):
            logging.info("Pure-Python Unity solution generator produced: %s", sln_path)
            return sln_path

    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".sln") or file.endswith(".slnx"):
                return os.path.join(root, file)

    return None  # No solution file found


def _find_unity_executable():
    """Return the path to a Unity editor executable, or None if not found."""
    # Allow override from environment
    explicit = os.environ.get("UNITY_EXECUTABLE_PATH")
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit

    candidates = [
        "unity",
        "unity-editor",
        "/opt/Unity/Editor/Unity",
        "/usr/bin/unity",
        "/usr/bin/unity-editor",
    ]
    for c in candidates:
        path = shutil.which(c) or c
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _run_unity_cli_build(repo_path, unity_project_root):
    """Optionally activate a license and run Unity Editor CLI to build the project.

    Controlled by env var `UNITY_BUILD_WITH_EDITOR` (truthy values enable).
    Other env vars:
      - UNITY_LICENSE_PATH: path inside the container to a .ulf license file
      - UNITY_BUILD_TARGET: e.g. StandaloneLinux64 (default)
      - UNITY_EXECUTABLE_PATH: explicit path to the Unity binary
    """
    if not os.environ.get("UNITY_BUILD_WITH_EDITOR"):
        return None

    unity_exec = _find_unity_executable()
    if not unity_exec:
        logging.warning("UNITY_BUILD_WITH_EDITOR requested but no Unity executable found in PATH or UNITY_EXECUTABLE_PATH")
        return None

    build_target = os.environ.get("UNITY_BUILD_TARGET", "StandaloneLinux64")
    unity_license = os.environ.get("UNITY_LICENSE_PATH")

    # Activate license if provided
    if unity_license:
        if os.path.isfile(unity_license):
            act_cmd = [unity_exec, "-batchmode", "-nographics", "-manualLicenseFile", unity_license, "-quit"]
            logging.info("Activating Unity license via: %s", " ".join(act_cmd))
            try:
                subprocess.run(act_cmd, check=True, cwd=unity_project_root)
            except subprocess.CalledProcessError as e:
                logging.warning("Unity license activation failed: %s", e)
        else:
            logging.warning("UNITY_LICENSE_PATH is set but file not found: %s", unity_license)

    # Run a generic build. Note: many projects require a custom build method;
    # this attempts a best-effort using Unity's CLI buildTarget switch.
    build_cmd = [
        unity_exec,
        "-batchmode",
        "-nographics",
        "-projectPath",
        unity_project_root,
        "-buildTarget",
        build_target,
        "-quit",
        "-logFile",
        "-",
    ]
    logging.info("Running Unity CLI build: %s", " ".join(build_cmd))
    try:
        result = subprocess.run(build_cmd, check=False, capture_output=True, text=True, cwd=unity_project_root)
        logging.debug("Unity build stdout:\n%s", result.stdout)
        logging.debug("Unity build stderr:\n%s", result.stderr)
        if result.returncode != 0:
            logging.warning("Unity CLI build exited with code %s", result.returncode)
        else:
            logging.info("Unity CLI build completed successfully for project: %s", unity_project_root)
    except Exception as e:
        logging.warning("Unity CLI build invocation failed: %s", e)



def _collect_unity_assemblies(repo_path):
    """
    Scans repo_path/Assets for .asmdef files and .cs files.

    Returns a dict:  assembly_name -> {"dir": abs_directory, "files": [abs_cs_paths]}

    Files that are not underneath any .asmdef directory are grouped into
    "Assembly-CSharp" placed at repo_path.
    """
    assets_dir = os.path.join(repo_path, "Assets")
    if not os.path.isdir(assets_dir):
        return {}

    # Map each asmdef directory to the assembly name declared inside the file.
    asmdef_dirs = {}  # abs_dir -> assembly_name
    for root, _, files in os.walk(assets_dir):
        for fname in files:
            if not fname.endswith(".asmdef"):
                continue
            asmdef_path = os.path.join(root, fname)
            try:
                with open(asmdef_path, "r", encoding="utf-8") as fh:
                    data = json.loads(fh.read())
                name = data.get("name") or os.path.splitext(fname)[0]
            except Exception:
                name = os.path.splitext(fname)[0]
            asmdef_dirs[root] = name

    def _get_asm(cs_abs):
        """Return (assembly_name, asmdef_dir) for a given .cs file path."""
        best_dir, best_len = None, -1
        for adir in asmdef_dirs:
            if cs_abs.startswith(adir + os.sep):
                if len(adir) > best_len:
                    best_dir, best_len = adir, len(adir)
        if best_dir:
            return asmdef_dirs[best_dir], best_dir
        return "Assembly-CSharp", repo_path

    assemblies = {}
    for root, dirs, files in os.walk(assets_dir):
        dirs[:] = [d for d in dirs if d not in ("Library", "Temp", "Logs")]
        for fname in files:
            if not fname.endswith(".cs"):
                continue
            cs_abs = os.path.join(root, fname)
            name, asm_dir = _get_asm(cs_abs)
            if name not in assemblies:
                assemblies[name] = {"dir": asm_dir, "files": []}
            assemblies[name]["files"].append(cs_abs)

    return assemblies


def _build_unity_csproj(assembly_name, cs_files, output_dir):
    """
    Writes an SDK-style .csproj for a single Unity assembly.
    Uses NoWarn to suppress missing-Unity-reference diagnostics.
    Returns the path to the written .csproj file.
    """
    items = "\n    ".join(
        f'<Compile Include="{os.path.relpath(f, output_dir).replace(os.sep, "/")}" />'
        for f in sorted(cs_files)
    )
    csproj_content = (
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <PropertyGroup>\n"
        "    <TargetFramework>netstandard2.1</TargetFramework>\n"
        "    <LangVersion>9.0</LangVersion>\n"
        "    <Nullable>enable</Nullable>\n"
        "    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>\n"
        "    <!-- Suppress missing-Unity-assembly warnings -->\n"
        "    <NoWarn>CS0012;CS0246;CS0436;CS1701;CS1702</NoWarn>\n"
        "  </PropertyGroup>\n"
        "  <ItemGroup>\n"
        '    <Compile Remove="**/*.cs" />\n'
        f"    {items}\n"
        "  </ItemGroup>\n"
        "</Project>\n"
    )
    csproj_path = os.path.join(output_dir, f"{assembly_name}.csproj")
    with open(csproj_path, "w", encoding="utf-8") as fh:
        fh.write(csproj_content)
    return csproj_path


def _build_unity_sln(repo_path, csproj_paths):
    """
    Writes a minimal Visual Studio .sln referencing all supplied .csproj paths.
    Returns the path to the written .sln file.
    """
    CS_PROJECT_TYPE = "{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}"

    project_blocks = []
    config_entries = []
    for csproj_path in csproj_paths:
        name = os.path.splitext(os.path.basename(csproj_path))[0]
        rel  = os.path.relpath(csproj_path, repo_path).replace(os.sep, "\\")
        guid = "{" + str(uuid.uuid4()).upper() + "}"
        project_blocks.append(
            f'Project("{CS_PROJECT_TYPE}") = "{name}", "{rel}", "{guid}"\nEndProject'
        )
        for cfg in ("Debug|Any CPU", "Release|Any CPU"):
            config_entries.append(f"\t\t{guid}.{cfg}.ActiveCfg = {cfg}")
            config_entries.append(f"\t\t{guid}.{cfg}.Build.0 = {cfg}")

    sln_lines = [
        "",
        "Microsoft Visual Studio Solution File, Format Version 12.00",
        "# Visual Studio Version 17",
        "VisualStudioVersion = 17.0.31903.59",
        "MinimumVisualStudioVersion = 10.0.40219.1",
        *project_blocks,
        "Global",
        "\tGlobalSection(SolutionConfigurationPlatforms) = preSolution",
        "\t\tDebug|Any CPU = Debug|Any CPU",
        "\t\tRelease|Any CPU = Release|Any CPU",
        "\tEndGlobalSection",
        "\tGlobalSection(ProjectConfigurationPlatforms) = postSolution",
        *config_entries,
        "\tEndGlobalSection",
        "EndGlobal",
    ]
    sln_path = os.path.join(repo_path, "GeneratedUnity.sln")
    with open(sln_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sln_lines) + "\n")
    return sln_path


def generate_unity_solution(repo_path):
    """
    Generates a Visual Studio .sln and per-assembly .csproj files for a Unity
    project without requiring the Unity editor or a Unity license.

    Reads Assets/ structure and .asmdef files to produce one SDK-style .csproj
    per assembly (plus a catch-all "Assembly-CSharp" project for any .cs files
    not covered by a .asmdef).  A single .sln at repo_path ties them together.

    Returns the path to the generated .sln, or None if no .cs files were found.
    """
    assemblies = _collect_unity_assemblies(repo_path)
    if not assemblies:
        logging.warning(
            "No .cs files found under Assets/ in %s — skipping Unity solution generation.",
            repo_path,
        )
        return None

    csproj_paths = []
    for asm_name, info in assemblies.items():
        output_dir = info["dir"]
        os.makedirs(output_dir, exist_ok=True)
        csproj_path = _build_unity_csproj(asm_name, info["files"], output_dir)
        csproj_paths.append(csproj_path)
        logging.info("Generated %s (%d file(s))", csproj_path, len(info["files"]))

    sln_path = _build_unity_sln(repo_path, csproj_paths)
    print(f"✅ Unity solution generated: {sln_path} ({len(csproj_paths)} project(s))")
    return sln_path


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
