import requests
import datetime
import json

# === Configuration ===
GITLAB_URL = "https://szofttech.inf.elte.hu/api/v4"
GROUP_ID = "szofttech-ab-2024"  # Change to your GitLab group ID
TOKEN = "glpat-nhX8ATn_JNnfKWsHyZkt"  # GitLab API token with read_repository permission
MILESTONE_WEEK = "2024-03-25"  # Change to the milestone week (YYYY-MM-DD)
MIN_BURST_COMMITS = 4  # Minimum commits in a single day to count as a burst
DAYS_AFTER_PAUSE = 2  # Number of days of no commits required after the burst 

HEADERS = {"PRIVATE-TOKEN": TOKEN}

# Convert milestone week to a datetime object
milestone_start = datetime.datetime.strptime(MILESTONE_WEEK, "%Y-%m-%d")
milestone_end = milestone_start + datetime.timedelta(days=6)  # End of the milestone week


def get_group_projects(group_id):
    """Fetch all project IDs from a GitLab group."""
    url = f"{GITLAB_URL}/groups/{group_id}/projects?include_subgroups=true&per_page=100"
    response = requests.get(url, headers=HEADERS)
    projects = response.json()
    return [project["id"] for project in projects] if isinstance(projects, list) else []


def get_commits(project_id, since=None, until=None):
    """Fetch commits for a project within a time range."""
    url = f"{GITLAB_URL}/projects/{project_id}/repository/commits"
    params = {"per_page": 100}
    
    if since:
        params["since"] = since.isoformat()
    if until:
        params["until"] = until.isoformat()

    response = requests.get(url, headers=HEADERS, params=params)
    commits = response.json()
    
    return commits if isinstance(commits, list) else []


def detect_burst_and_pause(project_id):
    """Detects the exact day of a burst and ensures no commits for DAYS_AFTER_PAUSE."""
    
    # Fetch all commits during the milestone week
    commits = get_commits(project_id, since=milestone_start, until=milestone_end)
    
    # Group commits by day
    commit_days = {}
    for commit in commits:
        commit_date = commit["created_at"][:10]  # Extract YYYY-MM-DD
        if commit_date not in commit_days:
            commit_days[commit_date] = []
        commit_days[commit_date].append(commit)

    # Find the burst day (highest commit count meeting threshold)
    burst_day = None
    last_commit_id = None
    for day, commit_list in sorted(commit_days.items()):
        if len(commit_list) >= MIN_BURST_COMMITS:
            burst_day = day
            last_commit_id = commit_list[0]["id"]  # Last commit of the burst
            break  # Stop after finding the first burst

    if not burst_day:
        return {
            "project_id": project_id,
            "milestone_week": MILESTONE_WEEK,
            "burst_day": None,
            "commits_on_burst_day": 0,
            "pause_detected": False,
            "status": "No Milestone",
            "last_commit_of_burst": None
        }

    # Check for inactivity after the burst
    burst_day_dt = datetime.datetime.strptime(burst_day, "%Y-%m-%d")
    pause_start = burst_day_dt + datetime.timedelta(days=1)
    pause_end = pause_start + datetime.timedelta(days=DAYS_AFTER_PAUSE - 1)

    commits_after = get_commits(project_id, since=pause_start, until=pause_end)
    pause_detected = len(commits_after) == 0  # No commits after the burst

    return {
        "project_id": project_id,
        "milestone_week": MILESTONE_WEEK,
        "burst_day": burst_day,
        "commits_on_burst_day": len(commit_days[burst_day]),
        "pause_detected": pause_detected,
        "status": "Confirmed Milestone" if pause_detected else "No Milestone",
        "last_commit_of_burst": last_commit_id
    }


def analyze_group_milestones():
    """Analyze all projects in the GitLab group for milestone detection."""
    project_ids = get_group_projects(GROUP_ID)
    results = {}

    for project_id in project_ids:
        print(f"Analyzing project {project_id}...")
        milestone_info = detect_burst_and_pause(project_id)
        results[project_id] = milestone_info

    # Save overall results
    with open("gitlab_milestones.json", "w") as f:
        json.dump(results, f, indent=4)

    print("Analysis complete! Results saved to gitlab_milestones.json")


# === Run Analysis ===
analyze_group_milestones()