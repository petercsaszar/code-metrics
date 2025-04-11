import os
import re
import json
import subprocess
import git
import yaml
import requests
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


def run_analyzers(repo_path):
    """Run the roslyn analyzers."""
    project_path = os.path.join(ANALYZER_DIR, ANALYZER_PROJECT_FILE)
    solution_path = find_solution_file(repo_path)
    if not solution_path:
        print("❌ No solution found.")
        return None

    print(f"🚀 Running analyzers for {repo_path} ...")

    command = [
        "dotnet", "run", "--project", project_path, "analyze", solution_path
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        match_bumpy = re.search(r"(\d+)\s+BR001", result.stdout)
        match_fpc = re.search(r"(\d+)\s+FPC001", result.stdout)
        match_lcom5 = re.search(r"(\d+)\s+LCOM5", result.stdout)

        bumpy_score = int(match_bumpy.group(1)) if match_bumpy else 0
        fpc_score = int(match_fpc.group(1)) if match_fpc else 0
        lcom5_score = int(match_lcom5.group(1)) if match_lcom5 else 0

        if "diagnostics found" not in result.stdout:
            print(f"❌ Error running analyzer: {result.stdout}")

        formatted_result = {
            "bumpy_score": bumpy_score,
            "fpc_score": fpc_score,
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
        repo_path = clone_repo(project_id)
        commit_id = project_data.get("last_commit_id")

        if not commit_id:
            continue

        checkout_commit(repo_path, commit_id)
        analysis_result = run_analyzers(repo_path)

        if analysis_result:
            results[project_id] = {
                "project_id": project_id,
                "commit_id": commit_id,
                "bumpy_score": analysis_result["bumpy_score"],
                "fpc_score": analysis_result["fpc_score"],
                "lcom5_score": analysis_result["lcom5_score"]
            }

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
            if file.endswith(".sln"):
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
    command = [
        UNITY_PATH, "-batchmode", "-quit", "-nographics", "-projectPath", repo_path, "-executeMethod", "UnityEditor.SyncVS.SyncSolution"
    ]
    try:
        subprocess.run(command, check=True)
        print("✅ Unity solution file generated.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating Unity solution: {e}")


if __name__ == "__main__":
    analyze_all_milestones()
