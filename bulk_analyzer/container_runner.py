import argparse
import contextlib
import io
import json
import os
import sys


def make_absolute(path):
    return os.path.abspath(path)


def normalize_repo_path(repo_path):
    return os.path.normpath(repo_path)


def main():
    parser = argparse.ArgumentParser(description="Run analyzers inside container and emit JSON results.")
    parser.add_argument("--repo-path", required=True, help="Absolute path to repository inside container")
    parser.add_argument("--solution-path", help="Optional solution path relative to repository root")
    parser.add_argument("--custom-build-command", help="Optional custom build command to execute prior to analysis")
    parser.add_argument("--msbuild-path", default=None, help="Optional override for MSBuild path")
    args = parser.parse_args()

    repo_path = normalize_repo_path(args.repo_path)
    solution_path = args.solution_path
    custom_build_command = args.custom_build_command

    # Import lazily so environment overrides can be applied first
    from bulk_analyzer import analyzer  # type: ignore

    if args.msbuild_path:
        analyzer.MSBUILD_DIR = args.msbuild_path
    else:
        analyzer.MSBUILD_DIR = os.environ.get("MSBUILD_PATH", "dotnet")

    analyzer.ANALYZER_DIR = make_absolute(analyzer.ANALYZER_DIR)
    log_buffer = io.StringIO()
    with contextlib.redirect_stdout(log_buffer):
        metrics = analyzer.run_builtin_roslyn_metrics(repo_path, solution_path, custom_build_command)
        custom = analyzer.run_analyzers(repo_path, solution_path, custom_build_command)

    logs = log_buffer.getvalue()
    if logs:
        sys.stderr.write(logs)
        if not logs.endswith("\n"):
            sys.stderr.write("\n")

    payload = {
        "custom": custom or {},
        "metrics": metrics or {},
    }

    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()
