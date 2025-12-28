import numpy as np
import yaml
import json
import os
import git
import re
import subprocess
import tempfile
import shutil
from glob import glob
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


# === Load Configuration ===
CONFIG_PATH = os.getenv("ANALYZER_CONFIG", os.getenv("CONFIG_PATH", "config.yml"))

with open(CONFIG_PATH, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

# === Configuration ===
REPO_LIST_FILE = config["public_analyzer"]["repository_list"]  # File containing repository URLs
ANALYZER_DIR = config["analyzer"]["project_dir"]
CLONE_DIR = config["public_analyzer"]["clone_dir"]
DOCKER_IMAGE = config.get("docker", {}).get("image", "code-metrics-analyzer")

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


def _workspace_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _to_container_path(host_path):
    root = _workspace_root()
    rel = os.path.relpath(host_path, root)
    return os.path.join("/workspace", rel.replace("\\", "/")).replace("\\", "/")


def run_analysis_in_container(repo_url, ref=None, solution_path=None, custom_build_command=None, timeout=None):
    """
    Clone the given `repo_url` inside a fresh temp dir mounted to the container at /work,
    checkout `ref` (tag/commit/branch) if provided, then run `bulk_analyzer.container_runner`
    against the in-container path `/work/repo`.
    Returns parsed JSON output from the container (or empty dict on failure).
    """
    workspace = _workspace_root()

    tempdir = tempfile.mkdtemp(prefix="release_")
    try:
        in_container_repo_path = "/work/repo"

        # Build shell script run inside container: clone, checkout ref if present, then run analyzer
        clone_and_run = (
            f"set -eu; "
            f"git clone {repo_url} {in_container_repo_path} || exit 1; "
        )
        if ref:
            clone_and_run += f"cd {in_container_repo_path} && git fetch --tags || true && git checkout {ref} || true; "

        clone_and_run += (
            f"/opt/venv/bin/python -m bulk_analyzer.container_runner "
            f"--repo-path {in_container_repo_path} "
        )
        if solution_path:
            clone_and_run += f"--solution-path {solution_path} "
        if custom_build_command:
            safe_cmd = custom_build_command.replace('"', '\\"')
            clone_and_run += f'--custom-build-command "{safe_cmd}" '

        docker_cmd = [
            "docker", "run", "--rm",
            # mount the per-run workdir and the analyzer workspace so the container can import bulk_analyzer
            "-v", f"{tempdir}:/work",
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace/bulk_analyzer",
            "-e", "ANALYZER_CONFIG=/workspace/bulk_analyzer/config.yml",
            "-e", "CONFIG_PATH=/workspace/bulk_analyzer/config.yml",
            "-e", "MSBUILD_PATH=dotnet",
            "-e", "PYTHONPATH=/workspace",
            "--entrypoint", "/bin/sh",
            DOCKER_IMAGE,
            "-c",
            clone_and_run
        ]

        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)

        if result.stderr:
            print(result.stderr, end="")

        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)

        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            # try to parse final line as JSON if logs were printed earlier
            lines = (result.stdout or "").strip().splitlines()
            if lines:
                try:
                    return json.loads(lines[-1])
                except Exception:
                    pass
            print("Failed to parse analyzer output from container")
            return {}
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)

def analyze_projects():
    """Analyze all projects with different thresholds."""
    projects = load_commit_list()

    results = {}

    for project in projects:
        repo_url = project["repo"]
        tag_list = project.get("tags", [])
        custom_build_command = project.get("custom_build_command", None)
        solution_path = project.get("solution_path", None)

        repo_name = get_repo_name(repo_url)
        project_id = repo_name if repo_name else repo_url
        results[project_id] = {}

        for i, tag_name in enumerate(tag_list):
            try:
                container_result = run_analysis_in_container(repo_url, ref=tag_name, solution_path=solution_path, custom_build_command=custom_build_command)
                analysis_result = container_result.get("custom", {})
                builtin_analysis_result = container_result.get("metrics", {})
                if analysis_result or builtin_analysis_result:
                    results[project_id][i] = {
                        "repo_url": repo_url,
                        "tag": tag_name,
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
                print(f"⚠️ Error analyzing tag {tag_name} in {repo_url}: {e}")

    # Save results
    with open("public_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    analyze_projects()
