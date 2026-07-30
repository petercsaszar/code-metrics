"""
LatestSnapshotEvaluation: Analyzes the HEAD of student projects' default branches.

Purpose: Evaluate practical usefulness of method-level metrics in current code.

This module orchestrates:
  - Fetching student projects from GitLab
  - Cloning/updating repositories
  - Checking out HEAD of the default branch (no milestone-based filtering)
  - Running the .NET CodeMetricsAnalyzer
  - Generating JSON and HTML reports

Unlike analyzer.py (milestone-based), this focuses on the latest commit and
method-level metric evaluation.
"""

import os
import re
import json
import subprocess
import shutil
import git
import yaml
import requests
try:
    from .dotnet_environment import ensure_dotnet_environment
except ImportError:
    from dotnet_environment import ensure_dotnet_environment
import logging
import argparse

# Configure logging
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_FILE = os.getenv("ANALYSIS_LOGFILE", os.path.join(WORKSPACE, "analysis_errors.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

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
CLONE_DIR = config["project"]["clone_dir"]

ANALYZER_DIR = config["analyzer"]["project_dir"]
MSBUILD_DIR = config["analyzer"]["msbuild_dir"]
ANALYZER_PROJECT_FILE = config["analyzer"]["project_file"]
CLOC_BINARY = config["analyzer"].get("cloc_path", "cloc")

HEADERS = {"PRIVATE-TOKEN": TOKEN}

# Globals for CLI-driven state
REPORT_OUTPUT = os.getenv("REPORT_OUTPUT", "latest_snapshot_results.json")
FORCE_REANALYZE = False


def _calculate_lines_of_code_fallback(repo_path, extensions=(".cs",), exclude_dirs=None):
    """Fallback LOC calculation: count non-empty lines in matching source files."""
    if exclude_dirs is None:
        exclude_dirs = {
            ".git", ".vs", "bin", "obj", "Library", "Packages", "Temp",
            "Logs", "UserSettings", "node_modules",
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
            ".git", ".vs", "bin", "obj", "Library", "Packages", "Temp",
            "Logs", "UserSettings", "node_modules",
        }

    cloc_binary = os.getenv("CLOC_PATH", CLOC_BINARY)
    cloc_available = shutil.which(cloc_binary) is not None

    if cloc_available:
        include_lang = "C#" if ".cs" in extensions else None
        exclude_dir_arg = ",".join(sorted(exclude_dirs))

        cloc_command = [
            cloc_binary, "--json", "--quiet", "--exclude-dir", exclude_dir_arg,
        ]
        if include_lang:
            cloc_command += ["--include-lang", include_lang]
        cloc_command.append(repo_path)

        try:
            result = subprocess.run(
                cloc_command, capture_output=True, text=True, check=False,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0 and result.stdout:
                cloc_output = json.loads(result.stdout)
                if "SUM" in cloc_output and "code" in cloc_output["SUM"]:
                    return int(cloc_output["SUM"]["code"])
            logging.warning(
                "cloc failed for %s (exit=%s), falling back. stderr=%s",
                repo_path, result.returncode, result.stderr.strip()
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
        return project_data["http_url_to_repo"]
    else:
        print(f"❌ Failed to fetch project {project_id} info: {response.text}")
        return None


def clone_repo(project_id, clone_base_dir=None):
    """Clone the GitLab repository, returning the path."""
    if clone_base_dir is None:
        clone_base_dir = CLONE_DIR

    repo_path = os.path.join(clone_base_dir, str(project_id))
    repo_url = get_project_info(project_id)
    if not repo_url:
        print(f"⚠ Skipping project {project_id} - Repository URL not found")
        return None

    # Add auth token
    repo_url = repo_url.replace("https://", f"https://oauth2:{TOKEN}@")

    if not os.path.exists(repo_path):
        print(f"🔄 Cloning repository {project_id} ...")
        os.makedirs(clone_base_dir, exist_ok=True)
        git.Repo.clone_from(repo_url, repo_path)
    else:
        print(f"✅ Repository {project_id} already exists.")

    return repo_path


def get_default_branch(repo_path):
    """Get the default branch name of the repository."""
    try:
        repo = git.Repo(repo_path)
        return repo.active_branch.name
    except Exception as e:
        logging.warning("Could not determine default branch for %s, assuming 'main': %s", repo_path, e)
        return "main"


def checkout_head(repo_path):
    """Checkout HEAD of the current branch (latest commit)."""
    try:
        repo = git.Repo(repo_path)
        repo.remotes.origin.pull()  # Update to latest
        print(f"✅ Repository {repo_path} updated to latest HEAD")
    except Exception as e:
        logging.warning("Could not pull latest for %s: %s", repo_path, e)

    try:
        subprocess.run(["git", "clean", "-xdf"], cwd=repo_path, check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠ Git clean failed: {e}")


def find_solution_file(repo_path):
    """Recursively search for a .sln file in the repository."""
    unity_project_root = _find_unity_project_root(repo_path)
    if unity_project_root:
        print("🎮 Detected Unity project.")
        # Try Python solution generator
        sln_path = generate_unity_solution(unity_project_root)
        if sln_path and os.path.isfile(sln_path):
            logging.info("Pure-Python Unity solution generator produced: %s", sln_path)
            return sln_path

    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".sln") or file.endswith(".slnx"):
                return os.path.join(root, file)

    return None


def _find_unity_project_root(repo_path):
    """Walk repo_path looking for ProjectSettings/ProjectVersion.txt."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in (".git", "Library", "Temp", "Logs")]
        if os.path.basename(root) == "ProjectSettings" and "ProjectVersion.txt" in files:
            return os.path.dirname(root)
    return None


def _collect_unity_assemblies(repo_path):
    """Collect Unity assembly definitions from Assets/."""
    assets_dir = os.path.join(repo_path, "Assets")
    if not os.path.isdir(assets_dir):
        return {}

    asmdef_dirs = {}
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
    """Write an SDK-style .csproj for a single Unity assembly."""
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
    """Write a minimal Visual Studio .sln referencing all .csproj paths."""
    import uuid
    CS_PROJECT_TYPE = "{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}"

    project_blocks = []
    config_entries = []
    for csproj_path in csproj_paths:
        name = os.path.splitext(os.path.basename(csproj_path))[0]
        rel = os.path.relpath(csproj_path, repo_path).replace(os.sep, "\\")
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
    """Generate a Visual Studio .sln for a Unity project without requiring the editor."""
    assemblies = _collect_unity_assemblies(repo_path)
    if not assemblies:
        logging.warning("No .cs files found under Assets/ in %s", repo_path)
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


def run_analyzers(repo_path, solution_path=None, report_output=None, history_dir=None):
    """Run the roslyn analyzers on a repository."""
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
        build_solution(repo_path, solution_path)
    except subprocess.CalledProcessError as e:
        logging.warning("Build error, trying analyzers anyway: %s", e)

    if os.path.exists(project_path):
        analyze_command = [
            "dotnet", "run", "--project", project_path, "analyze", solution_path
        ]
    else:
        bundled_dir = os.getenv("BUNDLED_ANALYZER_PATH", "/opt/CodeMetricsAnalyzer")
        dll_path = os.path.join(bundled_dir, "CodeMetricsAnalyzer.dll")
        if os.path.exists(dll_path):
            analyze_command = ["dotnet", dll_path, "analyze", solution_path]
        else:
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
        logging.error("Analyzer failed (exit %s)", result.returncode)
        logging.error("stdout:\n%s", result.stdout)
        logging.error("stderr:\n%s", result.stderr)
        return None

    # Extract metric counts from analyzer output
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

    return {
        "bumpy_score": bumpy_score,
        "fpc_score": fpc_score,
        "lcom4_score": lcom4_score,
        "lcom5_score": lcom5_score,
        "maintainability_index_score": maintainability_index_score,
        "cyclomatic_complexity_score": cyclomatic_complexity_score,
        "class_coupling_score": class_coupling_score,
        "lines_of_code": lines_of_code,
    }


def build_solution(repo_path, solution_path):
    """Build the solution."""
    ensure_dotnet_environment(repo_path)
    clean_command = ["dotnet", "clean", solution_path]
    subprocess.run(clean_command, capture_output=True, text=True, check=False)

    build_command = [
        "dotnet", "build", solution_path,
        "-p:EnableWindowsTargeting=true",
    ]
    subprocess.run(build_command, check=True, encoding="utf-8", errors="replace")
    subprocess.run(clean_command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")


def fetch_student_projects(group_id, subgroup_id=None):
    """Fetch list of student projects from GitLab group."""
    projects = []
    per_page = 100
    page = 1

    # Determine the API endpoint
    if subgroup_id:
        # Use subgroup endpoint
        api_url = f"{GITLAB_URL}/groups/{subgroup_id}/projects"
    else:
        # Use group endpoint
        api_url = f"{GITLAB_URL}/groups/{group_id}/projects"

    while True:
        params = {
            "per_page": per_page,
            "page": page,
            "include_subgroups": "true",
            "order_by": "name",
            "sort": "asc",
        }

        response = requests.get(api_url, headers=HEADERS, params=params)

        if response.status_code != 200:
            logging.error("Failed to fetch projects from GitLab: %s", response.text)
            break

        batch = response.json()
        if not batch:
            break

        projects.extend(batch)
        page += 1

    logging.info(f"Fetched {len(projects)} projects from GitLab group")
    return projects


def analyze_latest_snapshot(group_id, subgroup_id=None, report_output_base=None):
    """Main function: analyze latest snapshots of all student projects."""
    projects = fetch_student_projects(group_id, subgroup_id)

    if not projects:
        print("❌ No projects found in GitLab group")
        return {}

    clone_base_dir = os.path.join(CLONE_DIR, "latest_snapshot")

    results = {}

    for project in projects:
        try:
            project_id = project["id"]
            project_name = project["name"]

            print(f"\n📦 Analyzing project: {project_name} (ID: {project_id})")

            repo_path = clone_repo(project_id, clone_base_dir=clone_base_dir)
            if not repo_path:
                continue

            checkout_head(repo_path)

            # Derive per-project HTML report directory
            project_report_dir = (
                os.path.join(report_output_base, f"project_{project_id}")
                if report_output_base else None
            )

            analysis_result = run_analyzers(repo_path, report_output=project_report_dir)

            if analysis_result:
                lines_of_code = calculate_lines_of_code(repo_path)

                # Get git info for the HEAD commit
                try:
                    repo = git.Repo(repo_path)
                    head_commit = repo.head.commit
                    commit_hash = head_commit.hexsha
                    commit_message = head_commit.message.strip()
                    commit_author = str(head_commit.author)
                    commit_date = head_commit.committed_datetime.isoformat()
                except Exception as e:
                    logging.warning("Could not get git info for %s: %s", repo_path, e)
                    commit_hash = "unknown"
                    commit_message = "unknown"
                    commit_author = "unknown"
                    commit_date = ""

                results[project_id] = {
                    "project_id": project_id,
                    "project_name": project_name,
                    "commit_hash": commit_hash,
                    "commit_message": commit_message,
                    "commit_author": commit_author,
                    "commit_date": commit_date,
                    "metrics": analysis_result,
                    "lines_of_code": lines_of_code,
                }

                logging.info(
                    "Analyzed project %s (%s): %d lines of code, metrics: %s",
                    project_name, project_id, lines_of_code, analysis_result
                )

        except Exception as e:
            print(f"❌ Error analyzing project {project.get('name', 'unknown')}: {e}")
            logging.error("Error analyzing project %s: %s", project.get("id", "unknown"), e)

    return results


def _parse_args():
    parser = argparse.ArgumentParser(description="Latest snapshot analyzer runner")
    parser.add_argument("--report-output", help="Path to write analysis results", default=None)
    parser.add_argument("--force", action="store_true", help="Force reanalysis")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.report_output:
        REPORT_OUTPUT = args.report_output
    if args.force:
        FORCE_REANALYZE = True

    # Get group ID from config or environment
    group_id = config["gitlab"].get("group_id")
    subgroup_id = config["gitlab"].get("subgroup_id")

    if not group_id:
        print("[ERROR] GITLAB_GROUP_ID not set in config")
        exit(1)

    # Run analysis
    out_path = REPORT_OUTPUT
    out_dir = out_path if os.path.isdir(out_path) else os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    results = analyze_latest_snapshot(group_id, subgroup_id, report_output_base=out_dir)

    # Save results
    result_file = os.path.join(out_dir, "latest_snapshot_results.json")
    try:
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Results saved to {result_file}")
    except Exception as e:
        logging.error("Could not write results to %s: %s", result_file, e)

    # Summary
    print(f"\n📊 Analysis complete: {len(results)} project(s) analyzed")
    for project_id, result in results.items():
        print(f"  - {result['project_name']}: {result['lines_of_code']} LOC")
