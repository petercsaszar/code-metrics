import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import yaml


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def prepare_repos_list(repos_dir):
    p = Path(repos_dir)
    if not p.exists():
        raise FileNotFoundError(f"Repos directory not found: {repos_dir}")
    return [x for x in sorted(p.iterdir()) if x.is_dir()]


def run_container_for_repo(image, repo_path, config_path, output_dir, processed_commits_host=None, extra_env=None, msbuild_path=None):
    name = repo_path.name
    container_repo = f"/repos/{name}"
    container_out = f"/outputs/{name}.json"
    container_processed = "/opt/bulk_analyzer/processed_commits.json"

    mounts = [
        f"{str(repo_path)}:{container_repo}:ro",
        f"{str(config_path)}:/opt/bulk_analyzer/config.yml:ro",
        f"{str(output_dir)}:/outputs",
    ]
    if processed_commits_host:
        mounts.append(f"{str(processed_commits_host)}:{container_processed}")

    cmd = [
        "docker",
        "run",
        "--rm",
    ]

    for m in mounts:
        cmd += ["-v", m]

    # pass MSBuild path if provided
    envs = []
    if msbuild_path:
        envs += ["-e", f"MSBUILD_PATH={msbuild_path}"]
    # ensure analyzer picks up processed commits path env
    if processed_commits_host:
        envs += ["-e", f"PROCESSED_COMMITS_PATH={container_processed}"]

    if extra_env:
        for k, v in extra_env.items():
            envs += ["-e", f"{k}={v}"]

    cmd += envs

    # pass report-output inside container
    cmd += [image, "--repo-path", container_repo, "--report-output", container_out]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "repo": name,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "out_file": os.path.join(str(output_dir), f"{name}.json"),
        }
    except Exception as e:
        return {"repo": name, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Run bulk analyzer docker containers for local repos")
    parser.add_argument("--config", default="config.yml", help="Path to bulk_analyzer config.yml")
    parser.add_argument("--image", default=None, help="Docker image to run (overrides config)")
    parser.add_argument("--repos-dir", default=None, help="Directory containing student repos (overrides config)")
    parser.add_argument("--output-dir", default="./analysis_outputs", help="Host directory to write JSON outputs")
    parser.add_argument("--processed-commits", default=None, help="Host file to persist processed commits across runs")
    parser.add_argument("--concurrency", type=int, default=4, help="Parallel container runs")
    parser.add_argument("--msbuild-path", default=None, help="MSBuild path to pass into containers")
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

    repos_dir = args.repos_dir or os.path.join(os.path.dirname(cfg_path), cfg.get("project", {}).get("clone_dir", "repos"))
    repos = prepare_repos_list(repos_dir)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    processed_commits = Path(args.processed_commits) if args.processed_commits else None
    if processed_commits and not processed_commits.exists():
        # create empty JSON
        processed_commits.write_text("{}", encoding="utf-8")

    print(f"Running {len(repos)} repos with image {image} (concurrency={args.concurrency})")

    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(run_container_for_repo, image, p, cfg_path, out_dir, processed_commits, {}, args.msbuild_path) for p in repos]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            repo = res.get("repo")
            if res.get("returncode") == 0:
                print(f"✅ {repo} completed")
            else:
                print(f"❌ {repo} failed: {res.get('error') or res.get('stderr')[:200]}")

    # Write summary
    summary = {r.get("repo"): {"rc": r.get("returncode"), "out": r.get("out_file"), "error": r.get("error")} for r in results}
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
