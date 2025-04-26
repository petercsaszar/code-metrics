import os
import re
import json
import subprocess
import git
import yaml
import requests
import xml.etree.ElementTree as ET
from glob import glob
from milestone_commit_finder import get_milestone_commits

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

GITLAB_URL = config["gitlab"]["url"]
TOKEN = config["gitlab"]["token"]
BUMPY_ANALYZER_PATH = config.get("bumpy_analyzer_path", "./BumpyRoadAnalyzer")
MILESTONES = config["gitlab"]["milestone_keywords"]
CLONE_DIR = config["project"]["clone_dir"]

ANALYZER_DIR = config["analyzer"]["project_dir"]
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
    print(f"Checked out commit {commit_id}")

def add_metrics_package_to_all_projects(repo_path):
    """Adds Microsoft.CodeAnalysis.Metrics to all .csproj files in the repo."""
    print("📦 Adding Microsoft.CodeAnalysis.Metrics to all projects...")

    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".csproj"):
                project_path = os.path.join(root, file)
                print(f"➡️ Adding package to {project_path}")
                try:
                    subprocess.run(["dotnet", "add", project_path, "package", "Microsoft.CodeAnalysis.Metrics"],
                                   check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to add package to {project_path}: {e.stderr or e.stdout}")

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



def run_builtin_roslyn_metrics(repo_path):
    """Run Roslyn built-in metrics analyzer."""
    project_path = os.path.join(ANALYZER_DIR, ANALYZER_PROJECT_FILE)
    solution_path = find_solution_file(repo_path)
    if not solution_path:
        print("❌ No solution found.")
        return None

    print(f"🚀 Running built-in Roslyn metrics for {repo_path} ...")
    
    add_metrics_package_to_all_projects(repo_path)

    try:        
        build_command = [
        "dotnet", "build", solution_path
        ]
        subprocess.run(build_command, capture_output=True, text=True, check=True)
        
        analyze_command = [
        "dotnet", "msbuild", solution_path, "/t:Metrics"
        ]
        subprocess.run(analyze_command, capture_output=True, text=True, check=True)
    
        # Find all generated *.Metrics.xml files under this solution's directory
        metrics_files = glob(os.path.join(repo_path, "**", "*.Metrics.xml"), recursive=True)
        print(f"🔍 Found {len(metrics_files)} metrics files.")

        aggregated = aggregate_project_builtin_metrics(metrics_files)
        if aggregated:
            return aggregated
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running analyzer: {e}")
        return None
   

def run_analyzers(repo_path):
    """Run the roslyn analyzers."""
    project_path = os.path.join(ANALYZER_DIR, ANALYZER_PROJECT_FILE)
    solution_path = find_solution_file(repo_path)
    if not solution_path:
        print("❌ No solution found.")
        return None

    print(f"🚀 Running analyzers for {repo_path} ...")

    try:
        build_command = [
        "dotnet", "build", solution_path
        ]
        subprocess.run(build_command, capture_output=True, text=True, check=True)
        
        analyze_command = [
        "dotnet", "run", "--project", project_path, "analyze", solution_path
        ]
    
        result = subprocess.run(analyze_command, capture_output=True, text=True, check=True)
        match_bumpy = re.search(r"(\d+)\s+CMA0001", result.stdout)
        match_fpc = re.search(r"(\d+)\s+CMA0002", result.stdout)
        match_lcom5 = re.search(r"(\d+)\s+CMA0004", result.stdout)
        match_lcom4 = re.search(r"(\d+)\s+CMA0003", result.stdout)

        bumpy_score = int(match_bumpy.group(1)) if match_bumpy else 0
        fpc_score = int(match_fpc.group(1)) if match_fpc else 0
        lcom5_score = int(match_lcom5.group(1)) if match_lcom5 else 0
        lcom4_score = int(match_lcom4.group(1)) if match_lcom4 else 0

        if "diagnostics found" not in result.stdout and "diagnostic found" not in result.stdout:
            raise subprocess.CalledProcessError(returncode=result.returncode, cmd=result.args, output=result.stdout)

        formatted_result = {
            "bumpy_score": bumpy_score,
            "fpc_score": fpc_score,
            "lcom4_score": lcom4_score,
            "lcom5_score": lcom5_score
        }

        return formatted_result

        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running analyzer: {e}")
        return None


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
