import yaml
import json
import os
from milestone_commit_finder import get_projects, get_subgroups
from analyzer import clone_repo, run_analyzers, checkout_commit

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

# === Configuration ===
GITLAB_URL = config["gitlab"]["url"]
GROUP_ID = config["gitlab"]["group_id"] + ("%2f" + config["gitlab"]["subgroup_id"] if config["gitlab"]["subgroup_id"] else "")
TOKEN = config["gitlab"]["token"]  # GitLab API token with read_repository permission
ANALYZER_DIR = config["analyzer"]["project_dir"]
THRESHOLDS = list(range(1,10))

HEADERS = {"PRIVATE-TOKEN": TOKEN}

def get_all_projects():
    """Get all projects."""

    subgroup_ids = get_subgroups(GROUP_ID)
    if not subgroup_ids:
        subgroup_ids.append(GROUP_ID)

    projects = []

    for subgroup_id in subgroup_ids:
        print(f"Get projects for {subgroup_id}...")

        # Get projects inside this subgroup and its direct subgroups
        projects += get_projects(subgroup_id)

    return projects
   
def update_config(new_threshold):
    """Update the JSON config file with the given threshold."""
    config_path = os.path.join(ANALYZER_DIR, "appsettings.json")
    with open(config_path, "r", encoding="utf8") as f:
        conf = json.load(f)

    conf["BumpyRoadAnalysis"]["BumpynessThreshold"] = new_threshold
    conf["FunctionParameterCountAnalysis"]["ParameterCountThreshold"] = new_threshold
    conf["LCOM5Analysis"]["CohesionThreshold"] = new_threshold / 10 # normalize value beetween 0 and 1
    conf["LCOM4Analysis"]["CohesionThreshold"] = new_threshold

    with open(config_path, "w", encoding="utf8") as f:
        json.dump(conf, f, indent=4)

def analyze_projects():
    """Analyze all projects with different thresholds"""
    projects = get_all_projects()

    for threshold in THRESHOLDS:
        print(f"Checking threshold {threshold}...")
        update_config(threshold)

        results = {}

        for project in projects:
            repo_path = clone_repo(project)
            analysis_result = run_analyzers(repo_path)
            if (analysis_result):
                results[project] = {
                    "project_id": project,
                    "bumpy_score": analysis_result["bumpy_score"],
                    "fpc_score": analysis_result["fpc_score"],
                    "lcom4_score": analysis_result["lcom4_score"],
                    "lcom5_score": analysis_result["lcom5_score"]
                }

        # Define directory and file path
        results_dir = "threshold_analysis_data"
        results_file = f"analysis_results_{threshold}.json"

        # Ensure the directory exists
        os.makedirs(results_dir, exist_ok=True)

        # Save results
        with open(os.path.join(results_dir, results_file), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)


if __name__ == "__main__":
    analyze_projects()