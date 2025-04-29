import yaml
import json
import os
import git
from urllib.parse import urlparse
from analyzer import run_analyzers, checkout_commit

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

# === Configuration ===
REPO_LIST_FILE = config["public_analyzer"]["repository_list"]  # File containing repository URLs
ANALYZER_DIR = config["analyzer"]["project_dir"]
CLONE_DIR = config["public_analyzer"]["clone_dir"]

def get_all_projects():
    """Read repository URLs from file."""
    with open(REPO_LIST_FILE, "r", encoding="utf8") as f:
        projects = [line.strip() for line in f if line.strip()]
    return projects

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
                if "netcoreapp" in contents.lower() or "net5.0" in contents.lower() or "net6.0" in contents.lower() or "net7.0" in contents.lower() or "net8.0" in contents.lower()or "net9.0" in contents.lower():
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

    return selected


def analyze_projects():
    """Analyze all projects with different thresholds."""
    projects = get_all_projects()

    results = {}

    for project in projects:
        repo_path = clone_repo(project)
        commits = get_spaced_commits(repo_path)
        i = 0
        for commit in commits:
            checkout_commit(repo_path, commit)
            analysis_result = run_analyzers(repo_path)
            if analysis_result:
                repo_name = get_repo_name(project)
                project_id = repo_name if repo_name else project
                if project_id not in results:
                    results[project_id] = {}
                results[project_id][i] = {
                    "repo_url": project,
                    "bumpy_score": analysis_result.get("bumpy_score"),
                    "fpc_score": analysis_result.get("fpc_score"),
                    "lcom5_score": analysis_result.get("lcom5_score"),
                    "lcom4_score": analysis_result.get("lcom4_score"),
                    "MaintainabilityIndex": analysis_result.get("MaintainabilityIndex"),
                    "CyclomaticComplexity": analysis_result.get("CyclomaticComplexity"),
                    "ClassCoupling": analysis_result.get("ClassCoupling")
                }
            i += 1

    # Save results
    with open("public_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    analyze_projects()
