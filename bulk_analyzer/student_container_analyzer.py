"""
student_container_analyzer.py

Orchestrate Docker-based analysis of student projects from GitLab.
Analyzes each project at milestone commits, generates per-milestone JSON outputs,
and creates per-project HTML reports.

Usage:
    python -m bulk_analyzer.student_container_analyzer \\
        --config config.yml \\
        --image code-metrics-analyzer \\
        --output-dir ./analysis_outputs \\
        --concurrency 4
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
import requests

try:
    from .milestone_commit_finder import get_milestone_commits
except ImportError:
    from milestone_commit_finder import get_milestone_commits


def load_config(path):
    """Load YAML config file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_gitlab_projects_in_group(config):
    """
    Fetch all projects in the configured GitLab group/subgroup.
    Returns list of (project_id, project_name) tuples.
    """
    gitlab_url = config["gitlab"]["url"]
    token = config["gitlab"]["token"]
    group_id = config["gitlab"]["group_id"]
    subgroup_id = config["gitlab"].get("subgroup_id")

    headers = {"PRIVATE-TOKEN": token}

    if subgroup_id:
        # Fetch subgroup
        url = f"{gitlab_url}/groups/{group_id}/subgroups/{subgroup_id}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to fetch subgroup {subgroup_id}: {resp.text}")
            return []
        subgroup_data = resp.json()
        group_id_to_use = subgroup_data["id"]
    else:
        group_id_to_use = group_id

    # List all projects in the group (paginated)
    projects = []
    page = 1
    while True:
        url = f"{gitlab_url}/groups/{group_id_to_use}/projects?per_page=100&page={page}&include_subgroups=true"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        projects.extend([(p["id"], p["name"]) for p in batch])
        page += 1

    return projects


def run_container_for_milestone(image, project_id, milestone_commits, config_path, out_dir, processed_commits_host=None):
    """
    Run docker container to analyze a project at all its milestone commits.
    Returns dict with project_id, per-milestone outputs, and status.
    """
    result = {
        "project_id": project_id,
        "milestone_outputs": {},
        "errors": [],
    }

    # Ensure paths are absolute and properly formatted
    config_path = Path(config_path).resolve()
    out_dir = Path(out_dir).resolve()
    if processed_commits_host:
        processed_commits_host = Path(processed_commits_host).resolve()

    for milestone_idx, commit_id in enumerate(milestone_commits, start=1):
        try:
            # Create a temporary mount point for this run
            tmp_out = tempfile.mkdtemp(prefix=f"proj_{project_id}_m{milestone_idx}_")
            container_out = "/outputs"

            mounts = [
                f"{str(config_path)}:/opt/bulk_analyzer/config.yml:ro",
                f"{str(tmp_out)}:{container_out}",
            ]
            if processed_commits_host:
                mounts.append(f"{str(processed_commits_host)}:/processed_commits.json")

            cmd = [
                "docker",
                "run",
                "--rm",
            ]

            for m in mounts:
                cmd += ["-v", m]

            env_vars = [
                "-e",
                f"PROCESSED_COMMITS_PATH=/processed_commits.json",
            ]
            cmd += env_vars

            # Run container with analyzer.py to analyze this milestone
            cmd += [
                image,
                "--report-output",
                container_out,
                "--processed-commits-file",
                "/processed_commits.json",
            ]

            print(f"🔄 Running container for project {project_id} milestone {milestone_idx}...")
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if p.returncode != 0:
                result["errors"].append(f"Milestone {milestone_idx}: {p.stderr[:200]}")
                shutil.rmtree(tmp_out, ignore_errors=True)
                continue

            # Collect JSON and HTML outputs from the temp directory
            for f in Path(tmp_out).glob("*.json"):
                if f.name.startswith("analysis_results_"):
                    m_label = f.name.replace("analysis_results_", "").replace(".json", "")
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            data = json.load(fh)
                        result["milestone_outputs"][m_label] = data
                    except Exception as e:
                        result["errors"].append(f"Failed to read {f.name}: {e}")

            # Copy HTML reports to output directory
            for f in Path(tmp_out).glob("*.html"):
                try:
                    dest = Path(out_dir) / f.name
                    shutil.copy2(f, dest)
                    print(f"   Copied HTML report: {dest}")
                except Exception as e:
                    result["errors"].append(f"Failed to copy {f.name}: {e}")

            shutil.rmtree(tmp_out, ignore_errors=True)
            print(f"✅ Project {project_id} milestone {milestone_idx} completed")

        except subprocess.TimeoutExpired:
            result["errors"].append(f"Milestone {milestone_idx}: timeout")
        except Exception as e:
            result["errors"].append(f"Milestone {milestone_idx}: {str(e)}")

    return result





def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate Docker-based analysis of student projects from GitLab with HTML report generation."
    )
    parser.add_argument("--config", default="config.yml", help="Path to config.yml")
    parser.add_argument("--image", default=None, help="Docker image name (overrides config)")
    parser.add_argument("--output-dir", default="./analysis_outputs", help="Host directory for outputs")
    parser.add_argument("--processed-commits", default=None, help="Host file to persist processed commits")
    parser.add_argument("--concurrency", type=int, default=2, help="Parallel container runs")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config not found: {cfg_path}")
        sys.exit(1)

    cfg = load_config(str(cfg_path))
    image = args.image or cfg.get("docker", {}).get("image")
    if not image:
        print("Docker image not configured; set --image or config.docker.image")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    processed_commits = Path(args.processed_commits) if args.processed_commits else None
    if processed_commits and not processed_commits.exists():
        processed_commits.write_text("{}", encoding="utf-8")

    # Get milestone keywords from config
    milestones_keywords = cfg["gitlab"]["milestone_keywords"]

    # Fetch milestone commits for each project across all milestones
    all_projects_commits = {}
    for milestone_idx, milestone in enumerate(milestones_keywords, start=1):
        try:
            print(f"📋 Fetching milestone {milestone_idx} commits...")
            commit_data = get_milestone_commits(milestone)
            for project_id, project_info in commit_data.items():
                if project_id not in all_projects_commits:
                    all_projects_commits[project_id] = []
                all_projects_commits[project_id].append(project_info.get("last_commit_id"))
        except Exception as e:
            print(f"⚠️  Error fetching milestone {milestone_idx}: {e}")

    if not all_projects_commits:
        print("No projects found with milestone commits.")
        return

    # Get projects in GitLab group for metadata
    print("🔍 Fetching projects from GitLab for metadata...")
    projects = get_gitlab_projects_in_group(cfg)
    projects_by_id = {str(p[0]): p[1] for p in projects}
    print(f"Found {len(projects)} projects total")

    all_results = {}
    for project_id, commits in all_projects_commits.items():
        project_name = projects_by_id.get(str(project_id), f"Project {project_id}")
        all_results[str(project_id)] = {
            "name": project_name,
            "commits": commits,
        }

    if not all_results:
        print("No projects found with milestone commits.")
        return

    print(f"\n🚀 Running analysis for {len(all_results)} projects with {len(milestones_keywords)} milestones each...")

    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {
            ex.submit(
                run_container_for_milestone,
                image,
                project_id,
                v["commits"],
                cfg_path,
                out_dir,
                processed_commits,
            ): project_id
            for project_id, v in all_results.items()
        }
        for fut in as_completed(futures):
            project_id = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                if res.get("errors"):
                    print(f"❌ Project {project_id}: {', '.join(res['errors'][:2])}")
                else:
                    print(f"✅ Project {project_id} analysis completed")
            except Exception as e:
                print(f"❌ Project {project_id} failed: {e}")

    # Write summary
    summary = {
        r["project_id"]: {
            "milestones": len(r.get("milestone_outputs", {})),
            "errors": r.get("errors", []),
        }
        for r in results
    }
    summary_path = out_dir / "summary.json"
    try:
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\n✅ Summary written to {summary_path}")
    except Exception as e:
        print(f"Failed to write summary: {e}")

    print("\n🎉 Analysis complete!")
    print(f"Outputs: {out_dir}")
    print(f"  - JSON results: analysis_results_*.json")
    print(f"  - HTML reports: generated by CodeMetricsAnalyzer inside containers")


if __name__ == "__main__":
    main()
