import argparse
import contextlib
import io
import json
import os
import tempfile
import shutil
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
    parser.add_argument(
        "--analysis-mode",
        choices=["summary", "method"],
        default=os.environ.get("PUBLIC_ANALYSIS_MODE", "summary"),
        help="Choose aggregated summary scores or method-level diagnostics",
    )
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
    custom = {}
    method = []

    if args.analysis_mode == "method":
        from bulk_analyzer import method_analyzer  # type: ignore

        if args.msbuild_path:
            method_analyzer.MSBUILD_DIR = args.msbuild_path
        else:
            method_analyzer.MSBUILD_DIR = os.environ.get("MSBUILD_PATH", "dotnet")

        method_analyzer.ANALYZER_DIR = make_absolute(method_analyzer.ANALYZER_DIR)

        temp_dir = tempfile.mkdtemp(prefix="method_xml_")
        output_xml_path = os.path.join(temp_dir, "analysis.xml")
        try:
            with contextlib.redirect_stdout(log_buffer):
                ok = method_analyzer.run_analyzers_with_output(
                    repo_path,
                    output_xml_path,
                    solution_path,
                    custom_build_command,
                )
                if ok:
                    method = method_analyzer.parse_xml_output(output_xml_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        with contextlib.redirect_stdout(log_buffer):
            custom = analyzer.run_analyzers(repo_path, solution_path, custom_build_command)

    logs = log_buffer.getvalue()
    if logs:
        sys.stderr.write(logs)
        if not logs.endswith("\n"):
            sys.stderr.write("\n")

    payload = {
        "custom": custom or {},
        "method": method,
    }

    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()
