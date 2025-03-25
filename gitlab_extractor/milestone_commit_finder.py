import requests
import datetime
import json
import yaml
from fuzzywuzzy import fuzz

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

# === Configuration ===
GITLAB_URL = config["gitlab"]["url"]
GROUP_ID = config["gitlab"]["group_id"] + ("%2f" + config["gitlab"]["subgroup_id"] if config["gitlab"]["subgroup_id"] else "")
TOKEN = config["gitlab"]["token"]  # GitLab API token with read_repository permission

HEADERS = {"PRIVATE-TOKEN": TOKEN}


def get_subgroups(group_id):
    """Fetch all subgroups inside the main group."""
    url = f"{GITLAB_URL}/groups/{group_id}/subgroups?per_page=100"
    response = requests.get(url, headers=HEADERS)
    subgroups = response.json()
    return [subgroup["id"] for subgroup in subgroups] if isinstance(subgroups, list) else []


def get_projects(group_id):
    """Fetch all projects inside a subgroup and its direct subgroups (ignores deeper subgroups)."""
    projects = []
    
    # Get projects inside the group
    url = f"{GITLAB_URL}/groups/{group_id}/projects?per_page=100"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        projects.extend([project["id"] for project in response.json()])

    # Get sub-subgroups and their projects (but not deeper)
    subgroups = get_subgroups(group_id)
    for subgroup_id in subgroups:
        url = f"{GITLAB_URL}/groups/{subgroup_id}/projects?per_page=100"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            projects.extend([project["id"] for project in response.json()])

    return projects


def get_project_milestone_date(project_id, milestone_keywords):
    """Find the milestone that has the closest fuzzy name match to the given keywords."""
    url = f"{GITLAB_URL}/projects/{project_id}/milestones?per_page=100"
    response = requests.get(url, headers=HEADERS)
    milestones = response.json()

    if not isinstance(milestones, list) or not milestones:
        return None, 0  # No milestones found

    best_milestone = None
    best_similarity_score = 0  # Higher score = better match

    for milestone in milestones:
        milestone_title = milestone.get("title", "")
        due_date = milestone.get("due_date")  # Format: YYYY-MM-DD
        if not due_date:
            continue

        # Compute similarity score with each keyword
        for keyword in milestone_keywords:
            similarity_score = fuzz.partial_ratio(milestone_title.lower(), keyword.lower())

            # If this milestone is the best match so far, save it
            if (similarity_score > best_similarity_score and similarity_score > 70):
                best_similarity_score = similarity_score
                best_milestone = due_date

    return best_milestone, best_similarity_score  # Return the milestone with the best fuzzy name match with the match score


def get_commits(project_id, until):
    """Fetch all commits for a project up to a specific date."""
    url = f"{GITLAB_URL}/projects/{project_id}/repository/commits"
    params = {
        "per_page": 100,
        "until": until.isoformat()  # Get commits up to this date
    }

    response = requests.get(url, headers=HEADERS, params=params)
    commits = response.json()

    return commits if isinstance(commits, list) else []


def find_last_commit(project_id, milestone_date):
    """Find the last commit before or on the milestone date."""
    milestone_datetime = datetime.datetime.strptime(milestone_date, "%Y-%m-%d")
    
    commits = get_commits(project_id, until=milestone_datetime)

    if not commits:
        return None  # No commits found before or on milestone day

    return commits[0]["id"]  # Latest commit before or on milestone date


def get_subgroup_milestone_date(group_id, milestone_keywords):
    """Analyze all subgroups to find the milestone date."""

    # Get projects inside this subgroup
    project_ids = get_projects(group_id)

    # Try to find a project where the milestone date is set
    best_milestone_date = None
    best_milestone_date_score = 0
    for project_id in project_ids:
        milestone_date, milestone_date_score = get_project_milestone_date(project_id, milestone_keywords)
        if milestone_date_score > best_milestone_date_score:
           best_milestone_date_score = milestone_date_score
           best_milestone_date = milestone_date

    return best_milestone_date



def get_milestone_commits(milestone_keywords):
    """Analyze all projects, find milestones, and fetch all commits."""

    subgroup_ids = get_subgroups(GROUP_ID)
    if not subgroup_ids:
        subgroup_ids.append(GROUP_ID)

    results = {}

    for subgroup_id in subgroup_ids:
        print(f"Analyzing subgroup {subgroup_id}...")

        # Get projects inside this subgroup and its direct subgroups
        project_ids = get_projects(subgroup_id)
        milestone_date = get_subgroup_milestone_date(subgroup_id, milestone_keywords)

        if not milestone_date:
            print(f"❌ No close milestone match found for group {subgroup_id}")
            continue

        for project_id in project_ids:
            print(f"Fetching commits for project {project_id}...")

            # Get the last commit before or on the milestone date
            last_commit = find_last_commit(project_id, milestone_date)

            # Store results
            results[project_id] = {
                "project_id": project_id,
                "milestone_date": milestone_date,
                "last_commit_id": last_commit,
            }

            print(f"✅ Processed project {project_id}.")

    # with open("commit_data.json", "w") as f:
     #       json.dump(results, f, indent=4)
    
    return results
