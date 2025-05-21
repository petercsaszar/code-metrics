import numpy as np
import yaml
import json
import os
import git
import re
from glob import glob
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from analyzer import run_analyzers, run_builtin_roslyn_metrics, checkout_commit, find_solution_file

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

# === Configuration ===
REPO_LIST_FILE = config["public_analyzer"]["repository_list"]  # File containing repository URLs
ANALYZER_DIR = config["analyzer"]["project_dir"]
CLONE_DIR = config["public_analyzer"]["clone_dir"]

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

def analyze_projects():
    """Analyze all projects with different thresholds."""
    projects = load_commit_list()

    results = {}

    for project in projects:
        repo_url = project["repo"]
        tag_list = project["tags"]
        repo_path = clone_repo(repo_url)
        if not repo_path:
            continue

        repo_name = get_repo_name(repo_url)
        project_id = repo_name if repo_name else repo_url
        results[project_id] = {}

        repo = git.Repo(repo_path)
        for i, tag_name in enumerate(tag_list):
            try:
                if tag_name not in repo.tags:
                    print(f"⚠️ Tag '{tag_name}' not found in {repo_url}")
                    continue
                tag_ref = repo.tags[tag_name]
                commit = tag_ref.commit.hexsha
                checkout_commit(repo_path, commit)
                # remove_global_json(repo_path)
                # remove_vcxproj_entries(find_solution_file(repo_path))
                # clean_sln_nested_projects(find_solution_file(repo_path))
                patch_all_csproj_files(repo_path)
                analysis_result = run_analyzers(repo_path)
                builtin_analysis_result  = run_builtin_roslyn_metrics(repo_path)
                if analysis_result or builtin_analysis_result:
                    if project_id not in results:
                        results[project_id] = {}
                    results[project_id][i] = {
                        "repo_url": project,
                        "bumpy_score": analysis_result.get("bumpy_score", 0),
                        "fpc_score": analysis_result.get("fpc_score", 0),
                        "lcom5_score": analysis_result.get("lcom5_score", 0),
                        "lcom4_score": analysis_result.get("lcom4_score", 0),
                        "MaintainabilityIndex": builtin_analysis_result.get("MaintainabilityIndex", 0),
                        "CyclomaticComplexity": builtin_analysis_result.get("CyclomaticComplexity", 0),
                        "ClassCoupling": builtin_analysis_result.get("ClassCoupling", 0),
                        "SourceLines": builtin_analysis_result.get("SourceLines", 0)
                    }

            except Exception as e:
                print(f"⚠️ Error analyzing commit {commit} in {repo_url}: {e}")

    # Save results
    with open("public_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    analyze_projects()
