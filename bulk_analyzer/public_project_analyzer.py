import os
import git
import numpy as np
import yaml
import json
import os
import git
import re
import subprocess
import threading
import concurrent.futures
from datetime import datetime, timezone
import tempfile
import shutil
from glob import glob
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from datetime import datetime, timezone


# === Load Configuration ===
CONFIG_PATH = os.getenv("ANALYZER_CONFIG", os.getenv("CONFIG_PATH", "config.yml"))

with open(CONFIG_PATH, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

# === Configuration ===
REPO_LIST_FILE = config["public_analyzer"]["repository_list"]  # File containing repository URLs
ANALYZER_DIR = config["analyzer"]["project_dir"]
CLONE_DIR = config["public_analyzer"]["clone_dir"]
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", config.get("docker", {}).get("image", "code-metrics-analyzer"))
ANALYSIS_MODE = os.getenv("PUBLIC_ANALYSIS_MODE", config.get("public_analyzer", {}).get("analysis_mode", "summary")).lower()
if ANALYSIS_MODE not in ("summary", "method"):
    ANALYSIS_MODE = "summary"
OUTPUT_FILE = os.getenv("PUBLIC_OUTPUT_FILE", config.get("public_analyzer", {}).get("output_file", "public_analysis_results.json"))
# Container OS selection: prefer explicit env or config, default to linux
# Set `CONTAINER_OS` env or `docker.os` in config.yml to "windows" or "linux".
CONTAINER_OS = os.getenv("CONTAINER_OS", config.get("docker", {}).get("os", "linux"))

def load_commit_list():
    """Load a JSON file that contains a list of repos and their commit hashes."""
    with open(REPO_LIST_FILE, "r", encoding="utf8") as f:
        data = json.load(f)
    return data["repos"]

def get_repo_name(repo_url):
    """Extract the owner and project name from the URL."""
    parsed_url = urlparse(repo_url)
    path_parts = parsed_url.path.strip("/").split("/")
    
    if len(path_parts) < 2:
        print(f"⚠ Invalid repository URL: {repo_url}")
        return None

    owner, project_name = path_parts[0], path_parts[1]
    return f"{owner}_{project_name}"

def clone_repo(repo_url):
    """Clone the GitLab repository if not cloned yet, using the correct URL."""
    if not repo_url:
        print(f"⚠ Skipping project {repo_url} - Repository URL not found")
        return None
    
    project_folder = get_repo_name(repo_url)
    repo_path = os.path.join(CLONE_DIR, project_folder)

    if not os.path.exists(repo_path):
        print(f"🔄 Cloning repository {project_folder} from {repo_url}...")
        os.makedirs(CLONE_DIR, exist_ok=True)
        try:
            git.Repo.clone_from(repo_url, repo_path)
        except Exception as e:
            print(f"Some exception happened: {e}")
    else:
        print(f"✅ Repository {repo_url} already exists.")
        # repo = git.Repo(repo_path)
        # repo.remotes.origin.pull()

    return repo_path

def is_dotnet_core_project(repo, commit):
    """Check if a commit uses .NET Core in any .csproj file."""
    try:
        tree = commit.tree
        for blob in tree.traverse():
            if blob.path.endswith(".csproj"):
                contents = blob.data_stream.read().decode(errors="ignore")
                lc = contents.lower()
                if (
                    "netcoreapp" in lc
                    or "net5.0" in lc
                    or "net6.0" in lc
                    or "net7.0" in lc
                    or "net8.0" in lc
                    or "net9.0" in lc
                ):
                    return True
    except Exception as e:
        print(f"Error reading commit {commit.hexsha}: {e}")
    return False

def get_spaced_commits(repo_path, num_commits=5):
    """Return N spaced commits after the project starts using .NET Core."""
    repo = git.Repo(repo_path)
    head_commit = repo.head.commit

    all_commits = list(repo.iter_commits(head_commit, reverse=True))  # oldest to newest

    # Find first .NET Core commit
    core_start_index = None
    for i, commit in enumerate(all_commits):
        if is_dotnet_core_project(repo, commit):
            core_start_index = i
            break

    if core_start_index is None:
        print(f"⚠ Skipping project in {repo_path} - no .NET Core usage found.")
        return []

    filtered_commits = all_commits[core_start_index:]

    if len(filtered_commits) <= num_commits:
        return [commit.hexsha for commit in filtered_commits]

    step = len(filtered_commits) // (num_commits - 1)
    selected = [filtered_commits[0].hexsha]
    for i in range(1, num_commits - 1):
        selected.append(filtered_commits[i * step].hexsha)
    selected.append(filtered_commits[-1].hexsha)

    # return selected
    return filtered_commits

def get_spaced_commits_with_tags(repo_path, num_commits=5):
    """Return N spaced commits after the project starts using .NET Core."""
    repo = git.Repo(repo_path)

    tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)

    if len(tags) == 0:
        print("No tags found in repository.")
        return
    
    # If there are fewer tags than requested samples, just return all
    if len(tags) <= num_commits:
        selected_tags = tags
    else:
        # Pick num_samples tags spread evenly
        indices = np.linspace(0, len(tags) - 1, num_commits, dtype=int)
        selected_tags = [tags[i] for i in indices]

    # Now get the commits associated with each tag
    release_commits = [tag.commit for tag in selected_tags]

    return release_commits

def patch_csproj_to_ignore_nu1903(csproj_path):
    try:
        tree = ET.parse(csproj_path)
        root = tree.getroot()

        def get_or_create_pg():
            pgs = root.findall("PropertyGroup")
            return pgs[0] if pgs else ET.SubElement(root, "PropertyGroup")

        pg = get_or_create_pg()

        def append_or_create(tag, value):
            elem = pg.find(tag)
            if elem is None:
                elem = ET.SubElement(pg, tag)
                elem.text = value
            elif value not in elem.text:
                elem.text += f";{value}"

        append_or_create("WarningsNotAsErrors", "NU1903")
        append_or_create("NoWarn", "NU1903")

        tree.write(csproj_path, encoding="utf-8", xml_declaration=True)
        print(f"✅ Patched: {csproj_path}")
    except Exception as e:
        print(f"❌ Could not patch {csproj_path}: {e}")

def patch_all_csproj_files(repo_path):
    for csproj in glob(os.path.join(repo_path, "**", "*.csproj"), recursive=True):
        patch_csproj_to_ignore_nu1903(csproj)

def remove_vcxproj_entries(sln_path: str):
    with open(sln_path, encoding="utf-8") as f:
        lines = f.readlines()

    output_lines = []
    skip = False

    for line in lines:
        if re.match(r'^Project\(".*"\) = ".*", ".*\.vcxproj"', line):
            skip = True
            continue
        if skip and line.strip() == "EndProject":
            skip = False
            continue
        if not skip:
            output_lines.append(line)

    with open(sln_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    print(f"✅ Removed all .vcxproj entries from {sln_path}")

def remove_global_json(start_path="."):
    global_json_path = os.path.join(start_path, "global.json")
    if os.path.isfile(global_json_path):
        os.remove(global_json_path)
        print(f"🗑️ Removed: {global_json_path}")
    else:
        print("ℹ️ No global.json file found.")

def clean_sln_nested_projects(sln_path):
    with open(sln_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Collect all GUIDs of actual projects in the solution
    project_guids = set()
    project_regex = re.compile(r'^Project\(".*?"\) = ".*?", ".*?", "\{(.*?)\}"')
    for line in lines:
        match = project_regex.match(line)
        if match:
            project_guids.add(match.group(1).upper())

    cleaned_lines = []
    inside_nested = False

    for line in lines:
        if line.strip().startswith("GlobalSection(NestedProjects)"):
            inside_nested = True
            cleaned_lines.append(line)
            continue

        if inside_nested:
            if line.strip().startswith("EndGlobalSection"):
                inside_nested = False
                cleaned_lines.append(line)
                continue

            match = re.match(r'^\s*\{(.*?)\} = \{(.*?)\}', line)
            if match:
                child, parent = match.groups()
                if child.upper() in project_guids and parent.upper() in project_guids:
                    cleaned_lines.append(line)
                else:
                    print(f"Removing invalid nested project entry: {line.strip()}")
            else:
                cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)

    with open(sln_path, 'w', encoding='utf-8') as f:
        f.writelines(cleaned_lines)

    print("Finished cleaning solution file.")


def _workspace_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _to_container_path(host_path):
    root = _workspace_root()
    rel = os.path.relpath(host_path, root)
    return os.path.join("/workspace", rel.replace("\\", "/")).replace("\\", "/")


def run_analysis_in_container(repo_url, ref=None, solution_path=None, custom_build_command=None, timeout=None, analysis_mode="summary"):
    """
    Clone the given `repo_url` inside a fresh temp dir mounted to the container at /work,
    checkout `ref` (tag/commit/branch) if provided, then run `bulk_analyzer.container_runner`
    against the in-container path `/work/repo`.
    Returns parsed JSON output from the container (or empty dict on failure).
    """
    workspace = _workspace_root()

    # Container OS specifics
    is_windows = CONTAINER_OS.lower() == "windows"
    in_container_repo_path = "C:\\tmp\\repo" if is_windows else "/tmp/repo"

    # Build shell script run inside container: clone, checkout ref if present, then run analyzer
    if is_windows:
        clone_and_run = (
            "$ErrorActionPreference='Stop'; "
            f"git clone {repo_url} '{in_container_repo_path}' ; "
            f"Set-Location '{in_container_repo_path}'; "
        )
        if ref:
            clone_and_run += f"git fetch --tags ; try {{ git checkout {ref} }} catch {{}}; "
        clone_and_run += (
            f"& C:\\opt\\venv\\Scripts\\python.exe -m bulk_analyzer.container_runner "
            f"--repo-path '{in_container_repo_path}' "
            f"--analysis-mode {analysis_mode} "
        )
    else:
        clone_and_run = (
            f"set -eu; "
            f"git clone {repo_url} {in_container_repo_path} || exit 1; "
        )
        if ref:
            clone_and_run += f"cd {in_container_repo_path} && git fetch --tags || true && git checkout {ref} || true; "
        clone_and_run += (
            f"/opt/venv/bin/python -m bulk_analyzer.container_runner "
            f"--repo-path {in_container_repo_path} "
            f"--analysis-mode {analysis_mode} "
        )
    if solution_path:
        clone_and_run += f"--solution-path {solution_path} "
    if custom_build_command:
        safe_cmd = custom_build_command.replace('"', '\\"')
        clone_and_run += f'--custom-build-command "{safe_cmd}" '

    # Run fully inside the container (no host mounts); analyzer emits JSON to stdout
    # Honor logging level from host env (default INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO")

    if is_windows:
        docker_cmd = [
            "docker", "run", "--rm",
            "-e", f"LOG_LEVEL={log_level}",
            "-e", "ANALYZER_CONFIG=C:\\opt\\bulk_analyzer\\config.yml",
            "--entrypoint", r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            DOCKER_IMAGE,
            "-NoProfile", "-Command",
            clone_and_run
        ]
    else:
        docker_cmd = [
            "docker", "run", "--rm",
            "-e", f"LOG_LEVEL={log_level}",
            "-e", "ANALYZER_CONFIG=/opt/bulk_analyzer/config.yml",
            "--entrypoint", "/bin/sh",
            DOCKER_IMAGE,
            "-c",
            clone_and_run
        ]

    result = subprocess.run(docker_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    # Do not print container logs to the host console. If the container run failed,
    # write full stdout/stderr to the analysis logfile and print a short message.
    log_file = os.getenv("ANALYSIS_LOGFILE", os.path.join(workspace, "analysis_errors.log"))

    # Optional debug: dump container output to logfile even on success when enabled
    if os.getenv("DUMP_CONTAINER_OUTPUT", "") in ("1", "true", "True"):
        try:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"{datetime.now(timezone.utc).isoformat()}Z DEBUG: Container output for {repo_url} ref={ref}\n")
                lf.write("Command: " + " ".join(docker_cmd) + "\n")
                lf.write("STDOUT:\n" + (result.stdout or "") + "\n")
                lf.write("STDERR:\n" + (result.stderr or "") + "\n\n")
        except Exception:
            pass

    if result.returncode != 0:
        try:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"{datetime.now(timezone.utc).isoformat()}Z ERROR: Container run failed for {repo_url} ref={ref}\n")
                lf.write("Command: " + " ".join(docker_cmd) + "\n")
                lf.write("STDOUT:\n" + (result.stdout or "") + "\n")
                lf.write("STDERR:\n" + (result.stderr or "") + "\n\n")
        except Exception:
            pass

        print(f"Container run failed for {repo_url} {ref}. See {log_file}")
        return {}

    # On success: try to parse JSON output. If logs were printed before JSON, parse last line.
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        lines = (result.stdout or "").strip().splitlines()
        if lines:
            try:
                return json.loads(lines[-1])
            except Exception:
                pass
        # If parsing fails, write the full output to logfile for debugging but do not print to console
        try:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"{datetime.now(timezone.utc).isoformat()}Z WARN: Failed to parse JSON output for {repo_url} ref={ref}\n")
                lf.write("STDOUT:\n" + (result.stdout or "") + "\n")
                lf.write("STDERR:\n" + (result.stderr or "") + "\n\n")
        except Exception:
            pass
        return {}

# === Thresholds Configuration ===
THRESHOLDS = {
    "BumpyRoadAnalysis": {
        "BumpynessThreshold": 5
    },
    "FunctionParameterCountAnalysis": {
        "ParameterCountThreshold": 3
    },
    "LCOM5Analysis": {
        "CohesionThreshold": 0.3,
        "MinimumMethodCount": 2,
        "MinimumFieldCount": 1
    },
    "LCOM4Analysis": {
        "CohesionThreshold": 5,
        "MinimumMethodCount": 2,
        "MinimumFieldCount": 1
    },
    "MaintainabilityIndexAnalysis": {
        "MinimumMaintainabilityIndex": 65
    },
    "CyclomaticComplexityAnalysis": {
        "MaximumComplexity": 10
    },
    "ClassCouplingAnalysis": {
        "MaximumClassCoupling": 9
    }
}

def _passes_threshold(diagnostic: dict) -> bool:
    """
    Check if a diagnostic passes the configured thresholds.
    Returns True if the diagnostic should be included (i.e., it violates the threshold).
    """
    metric_name = diagnostic.get("metric_name")
    metric_value = diagnostic.get("metric_value")
    diagnostic_id = diagnostic.get("diagnostic_id")
    
    if metric_value is None or metric_name is None:
        # If we can't parse the metric, include it by default
        return True
    
    # CMA0001 - Bumpy Road Analysis
    if diagnostic_id == "CMA0001" or metric_name == "bumpy_road_score":
        threshold = THRESHOLDS["BumpyRoadAnalysis"]["BumpynessThreshold"]
        return metric_value >= threshold
    
    # CMA0002 - Function Parameter Count Analysis
    if diagnostic_id == "CMA0002" or metric_name == "parameter_count":
        threshold = THRESHOLDS["FunctionParameterCountAnalysis"]["ParameterCountThreshold"]
        return metric_value > threshold
    
    # CMA0005 - Maintainability Index Analysis
    if diagnostic_id == "CMA0005" or metric_name == "maintainability_index":
        threshold = THRESHOLDS["MaintainabilityIndexAnalysis"]["MinimumMaintainabilityIndex"]
        return metric_value < threshold
    
    # CMA0006 - Cyclomatic Complexity Analysis
    if diagnostic_id == "CMA0006" or metric_name == "cyclomatic_complexity":
        threshold = THRESHOLDS["CyclomaticComplexityAnalysis"]["MaximumComplexity"]
        return metric_value > threshold
    
    # CMA0003 - LCOM4 Analysis
    if diagnostic_id == "CMA0003" or metric_name == "lcom4_score":
        threshold = THRESHOLDS["LCOM4Analysis"]["CohesionThreshold"]
        return metric_value > threshold
    
    # CMA0004 - LCOM5 Analysis
    if diagnostic_id == "CMA0004" or metric_name == "lcom5_score":
        threshold = THRESHOLDS["LCOM5Analysis"]["CohesionThreshold"]
        return metric_value > threshold
    
    # CMA0007 - Class Coupling Analysis
    if diagnostic_id == "CMA0007" or metric_name == "class_coupling":
        threshold = THRESHOLDS["ClassCouplingAnalysis"]["MaximumClassCoupling"]
        return metric_value > threshold
    
    # If we can't determine the threshold, include it
    return True

def _count_methods_and_classes(diagnostics: list) -> tuple[int, int]:
    """
    Count unique methods and classes from the diagnostic list.
    Returns (method_count, class_count)
    """
    methods = set()
    classes = set()
    
    for diagnostic in diagnostics:
        symbol = diagnostic.get("symbol")
        if not symbol:
            continue
        
        diagnostic_id = diagnostic.get("diagnostic_id")
        
        # LCOM4 and LCOM5 are class-level diagnostics
        if diagnostic_id in ("CMA0003", "CMA0004"):
            classes.add(symbol)
        else:
            methods.add(symbol)
    
    return len(methods), len(classes)

def analyze_projects():
    """Analyze all projects with all methods/classes, then apply threshold filtering."""
    projects = load_commit_list()

    results = {}

    # concurrency setting (number of parallel containers)
    concurrency = config.get("public_analyzer", {}).get("concurrency", 6)

    # build list of tasks: (project, index, tag)
    tasks = []
    for project in projects:
        repo_url = project["repo"]
        tag_list = project.get("tags", [])
        custom_build_command = project.get("custom_build_command", None)
        solution_path = project.get("solution_path", None)

        repo_name = get_repo_name(repo_url)
        project_id = repo_name if repo_name else repo_url
        results[project_id] = {}

        for i, tag_name in enumerate(tag_list):
            tasks.append((project_id, repo_url, i, tag_name, solution_path, custom_build_command))

    lock = threading.Lock()

    def _run_task(task):
        project_id, repo_url, i, tag_name, solution_path, custom_build_command = task
        try:
            container_result = run_analysis_in_container(
                repo_url,
                ref=tag_name,
                solution_path=solution_path,
                custom_build_command=custom_build_command,
                analysis_mode=ANALYSIS_MODE,
            )
            return (project_id, repo_url, i, tag_name, container_result, None)
        except Exception as e:
            return (project_id, repo_url, i, tag_name, None, e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(_run_task, t): t for t in tasks}
        for fut in concurrent.futures.as_completed(futures):
            project_id, repo_url, i, tag_name, container_result, err = fut.result()
            if err:
                print(f"⚠️ Error analyzing tag {tag_name} in {project_id}: {err}")
                continue

            if ANALYSIS_MODE == "method":
                # Get ALL diagnostics (no filtering by threshold yet)
                all_diagnostics = container_result.get("method", []) if container_result else []
                
                if all_diagnostics:
                    # Count total methods and classes
                    total_methods, total_classes = _count_methods_and_classes(all_diagnostics)
                    
                    # Filter diagnostics by threshold
                    filtered_diagnostics = [d for d in all_diagnostics if _passes_threshold(d)]
                    
                    # Count filtered methods and classes
                    filtered_methods, filtered_classes = _count_methods_and_classes(filtered_diagnostics)
                    
                    with lock:
                        results.setdefault(project_id, {})
                        results[project_id][i] = {
                            "repo_url": repo_url,
                            "tag": tag_name,
                            "all_diagnostics_count": len(all_diagnostics),
                            "filtered_diagnostics_count": len(filtered_diagnostics),
                            "summary": {
                                "all": {
                                    "method_count": total_methods,
                                    "class_count": total_classes,
                                },
                                "filtered": {
                                    "method_count": filtered_methods,
                                    "class_count": filtered_classes,
                                }
                            },
                            "diagnostics": filtered_diagnostics,
                        }
            else:
                analysis_result = container_result.get("custom", {}) if container_result else {}

                if analysis_result:
                    with lock:
                        results.setdefault(project_id, {})
                        results[project_id][i] = {
                            "repo_url": repo_url,
                            "tag": tag_name,
                            "bumpy_score": analysis_result.get("bumpy_score", 0),
                            "fpc_score": analysis_result.get("fpc_score", 0),
                            "lcom5_score": analysis_result.get("lcom5_score", 0),
                            "lcom4_score": analysis_result.get("lcom4_score", 0),
                            "maintainability_index_score": analysis_result.get("maintainability_index_score", 0),
                            "cyclomatic_complexity_score": analysis_result.get("cyclomatic_complexity_score", 0),
                            "class_coupling_score": analysis_result.get("class_coupling_score", 0),
                        }

    # Save results
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    analyze_projects()
