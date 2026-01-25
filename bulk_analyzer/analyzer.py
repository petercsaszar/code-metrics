import os
import re
import json
import subprocess
import git
import yaml
import requests
import xml.etree.ElementTree as ET
from glob import glob
from .milestone_commit_finder import get_milestone_commits
from .dotnet_environment import ensure_dotnet_environment
import logging

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

HEADERS = {"PRIVATE-TOKEN": TOKEN}

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

def get_metrics_executable():
    """Get path to Metrics executable (bundled or system)."""
    # Check bundled locations first
    bundled_paths = [
        os.getenv("METRICS_PATH"),  # Allow override via env var
        "C:\\opt\\metrics\\Metrics.exe",  # Windows container
        "C:\\Program Files\\Metrics\\Metrics.exe",  # Windows system
    ]
    
    for path in bundled_paths:
        if path and os.path.isfile(path):
            return path
    
    # Fallback: try 'Metrics' in PATH
    try:
        result = subprocess.run(["where", "Metrics"],
                              capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    raise FileNotFoundError("Metrics executable not found. Please ensure it is bundled or installed.")

def aggregate_project_builtin_metrics(metrics_files):
    """Aggregate and average project metrics from multiple metrics.xml files."""
    sum_metrics = {
        "MaintainabilityIndex": 0,
        "CyclomaticComplexity": 0,
        "ClassCoupling": 0,
        "DepthOfInheritance": 0,
    }

    total_metrics = {
        "SourceLines": 0,
        "ExecutableLines": 0,
    }

    contributing_projects = 0

    for file in metrics_files:
        try:
            tree = ET.parse(file)
            root = tree.getroot()
            metrics = root.find(".//Metrics")
            if metrics is None:
                continue

            for metric in metrics.findall("Metric"):
                name = metric.attrib.get("Name")
                value = metric.attrib.get("Value")
                if name in sum_metrics:
                    sum_metrics[name] += int(value)
                elif name in total_metrics:
                    total_metrics[name] += int(value)

            contributing_projects += 1

        except Exception as e:
            print(f"⚠️ Error parsing {file}: {e}")

    if contributing_projects == 0:
        return None

    # Compute averages
    averaged_metrics = {
        name: round(value / contributing_projects)
        for name, value in sum_metrics.items()
    }

    # Merge totals
    averaged_metrics.update(total_metrics)

    return averaged_metrics

def run_builtin_roslyn_metrics(repo_path, solution_path=None, custom_build_command=None):
    """Run Roslyn built-in metrics analyzer using Metrics.exe."""
    if not solution_path:
        solution_path = find_solution_file(repo_path)
    else:
        solution_path = os.path.join(repo_path, solution_path)
    if not solution_path:
        print("❌ No solution found.")
        return None

    print(f"🚀 Running built-in Roslyn metrics for {repo_path} ...")

    try:
        build_solution(repo_path, solution_path, custom_build_command)
    except subprocess.CalledProcessError as e:
        logging.warning("Build error, attempting to run metrics anyway: %s", e)

    try:
        metrics_exe = get_metrics_executable()
    except FileNotFoundError as e:
        logging.error("Metrics tool not found: %s", e)
        return None

    # Run Metrics.exe on the solution
    output_xml = os.path.join(repo_path, "metrics_output.xml")
    analyze_command = [
        metrics_exe,
        f"/solution:{solution_path}",
        f"/out:{output_xml}"
    ]
    logging.info("Running Metrics.exe command: %s", " ".join(analyze_command))

    # Ensure Metrics.exe uses the SDK dotnet instead of any auto-installed dotnet
    env = os.environ.copy()
    # Point to SDK dotnet location (Windows container)
    sdk_dotnet_dir = r"C:\Program Files\dotnet"
    if os.path.isdir(sdk_dotnet_dir):
        # Prepend SDK dotnet to PATH so it's found first
        env["PATH"] = sdk_dotnet_dir + os.pathsep + env.get("PATH", "")
        env["DOTNET_ROOT"] = sdk_dotnet_dir
        # Disable automatic dotnet installation
        env["DOTNET_INSTALL_DIR"] = sdk_dotnet_dir
        env["DOTNET_MULTILEVEL_LOOKUP"] = "0"  # Prevent searching other locations
        logging.debug("Using SDK dotnet from %s", sdk_dotnet_dir)

    result = subprocess.run(
        analyze_command,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    logging.debug("Metrics.exe exit=%s stdout=\n%s\nstderr=\n%s", result.returncode, result.stdout, result.stderr)

    if result.returncode != 0:
        logging.error("Metrics.exe failed with exit code %s", result.returncode)
        return None

    # Parse the output XML
    if not os.path.isfile(output_xml):
        logging.warning("Metrics.exe did not generate output file: %s", output_xml)
        return None

    aggregated = aggregate_project_builtin_metrics([output_xml])
    if aggregated:
        try:
            os.remove(output_xml)
        except Exception:
            pass
        return aggregated

    return None
   

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

    bumpy_score = int(match_bumpy.group(1)) if match_bumpy else 0
    fpc_score = int(match_fpc.group(1)) if match_fpc else 0
    lcom5_score = int(match_lcom5.group(1)) if match_lcom5 else 0
    lcom4_score = int(match_lcom4.group(1)) if match_lcom4 else 0

    formatted_result = {
        "bumpy_score": bumpy_score,
        "fpc_score": fpc_score,
        "lcom4_score": lcom4_score,
        "lcom5_score": lcom5_score
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


    results = {}

    for project_id, project_data in commit_data.items():
        try:
            repo_path = clone_repo(project_id)
            commit_id = project_data.get("last_commit_id")

            if not commit_id or not repo_path:
                continue

            checkout_commit(repo_path, commit_id)
            analysis_result = run_analyzers(repo_path)
            builtin_analysis_result  = run_builtin_roslyn_metrics(repo_path)

            if analysis_result:
                results[project_id] = {
                    "project_id": project_id,
                    "commit_id": commit_id,
                    "bumpy_score": analysis_result["bumpy_score"],
                    "fpc_score": analysis_result["fpc_score"],
                    "lcom5_score": analysis_result["lcom5_score"],
                    "lcom4_score": analysis_result["lcom4_score"],
                    "MaintainabilityIndex": builtin_analysis_result["MaintainabilityIndex"],
                    "CyclomaticComplexity": builtin_analysis_result["CyclomaticComplexity"],
                    "ClassCoupling": builtin_analysis_result["ClassCoupling"],
                    "DepthOfInheritance": builtin_analysis_result["DepthOfInheritance"],
                    "SourceLines": builtin_analysis_result["SourceLines"],
                    "ExecutableLines": builtin_analysis_result["ExecutableLines"],
                }
        except Exception as e:
            print(f"❌ Error analyzing project {project_id}: {e}")


    return results

def analyze_all_milestones():
    """Analyze all milestone commits dynamically."""

    ind = 1
    for milestone in MILESTONES:
        milestone_results = analyze_milestone(milestone)

        with open(f"analysis_results_{ind}.json", "w") as f:
            json.dump(milestone_results, f, indent=4)
        ind = ind + 1

    print("✅ Bumpy Road Analysis complete! Results saved to files.")

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
    """Update the Unity Editor version"""
    version_file = os.path.join(project_path, "ProjectSettings", "ProjectVersion.txt")

    if not os.path.isfile(version_file):
        print(f"[ERROR] Couldn't find ProjectVersion.txt at: {version_file}")
        return

    with open(version_file, "w") as f:
        f.write(f"m_EditorVersion: {UNITY_VERSION}\n")

    print(f"[OK] Updated Unity version to {UNITY_VERSION} in {version_file}")


if __name__ == "__main__":
    analyze_all_milestones()
