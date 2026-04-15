"""
method_xml_analyzer.py

Runs CodeMetricsAnalyzer with the --output flag to produce per-run XML files,
then accumulates all generated XML files into a unified method-level dataset.

The accumulated output is a JSON file where each entry describes a single
diagnostic violation at the method (or class) level, enriched with:
  - project / milestone context
  - method / class name   (parsed from the diagnostic message)
  - numeric metric value  (parsed from the diagnostic message)
  - source file & location

Usage (standalone):
    python -m bulk_analyzer.method_xml_analyzer
"""

import os
import re
import json
import subprocess
import plistlib
import xml.etree.ElementTree as ET
import yaml
import logging
import sys

try:
    from .analyzer import (
        clone_repo,
        checkout_commit,
        build_solution,
        find_solution_file,
    )
    from .milestone_commit_finder import get_milestone_commits
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)

    local_config = os.path.join(current_dir, "config.yml")
    if "ANALYZER_CONFIG" not in os.environ and os.path.exists(local_config):
        os.environ["ANALYZER_CONFIG"] = local_config

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    from bulk_analyzer.analyzer import (
        clone_repo,
        checkout_commit,
        build_solution,
        find_solution_file,
    )
    from bulk_analyzer.milestone_commit_finder import get_milestone_commits

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_FILE = os.getenv("ANALYSIS_LOGFILE", os.path.join(WORKSPACE, "analysis_errors.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = os.getenv("ANALYZER_CONFIG", os.getenv("CONFIG_PATH", "config.yml"))

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    _config = yaml.safe_load(_f)

MILESTONES = _config["gitlab"]["milestone_keywords"]
ANALYZER_DIR = _config["analyzer"]["project_dir"]
ANALYZER_PROJECT_FILE = _config["analyzer"]["project_file"]
MSBUILD_DIR = _config["analyzer"].get("msbuild_dir", "")

# Optional CodeChecker export for visualization (no CodeChecker analyzers run)
_codechecker_cfg = _config.get("codechecker", {}) or {}
CODECHECKER_EXPORT_ENABLED = bool(_codechecker_cfg.get("enabled", False))
CODECHECKER_EXPORT_DIR = os.getenv(
    "CODECHECKER_EXPORT_DIR",
    _codechecker_cfg.get("export_dir", os.path.join(WORKSPACE, "codechecker_reports")),
)
CODECHECKER_EXPORT_PLIST = bool(_codechecker_cfg.get("export_plist", True))
CODECHECKER_EXPORT_JSON = bool(_codechecker_cfg.get("export_json", True))

# Directory where per-run XML output files are stored
XML_OUTPUT_DIR = os.getenv("XML_OUTPUT_DIR", os.path.join(WORKSPACE, "xml_outputs"))

# Final accumulated results file
ACCUMULATED_OUTPUT = os.getenv(
    "ACCUMULATED_OUTPUT",
    os.path.join(WORKSPACE, "method_analysis_results.json"),
)

# ---------------------------------------------------------------------------
# Regex patterns for extracting the symbol name and numeric value from each
# diagnostic message format (see DiagnosticDescriptors.cs).
# ---------------------------------------------------------------------------
_METHOD_PATTERNS: list[tuple[str, re.Pattern]] = [
    # CMA0001 – Bumpy Road:        "Method 'X' has a high bumpy road score (1.23)"
    ("bumpy_road_score",       re.compile(r"Method '([^']+)' has a high bumpy road score \(([\d.]+)\)")),
    # CMA0002 – FPC:               "Method 'X' has N parameters, which exceeds the defined threshold of M"
    ("parameter_count",        re.compile(r"Method '([^']+)' has (\d+) parameters")),
    # CMA0005 – Maintainability:   "Method 'X' has a low maintainability index (45.67)"
    ("maintainability_index",  re.compile(r"Method '([^']+)' has a low maintainability index \(([\d.]+)\)")),
    # CMA0006 – Cyclomatic:        "Method 'X' has a high cyclomatic complexity (8)"
    ("cyclomatic_complexity",  re.compile(r"Method '([^']+)' has a high cyclomatic complexity \(([\d.]+)\)")),
    # CMA0003 – LCOM4 (class):     "Class 'X' has a high LCOM4 score (2.00)"
    ("lcom4_score",            re.compile(r"Class '([^']+)' has a high LCOM4 score \(([\d.]+)\)")),
    # CMA0004 – LCOM5 (class):     "Class 'X' has a high LCOM5 score (0.75)"
    ("lcom5_score",            re.compile(r"Class '([^']+)' has a high LCOM5 score \(([\d.]+)\)")),
    # CMA0007 – ClassCoupling:     "'X' has a high class coupling value (12)"
    ("class_coupling",         re.compile(r"'([^']+)' has a high class coupling value \(([\d.]+)\)")),
]


def _to_codechecker_severity(severity: str | None) -> str:
    """Map generic severities to CodeChecker severities."""
    sev = (severity or "").strip().lower()
    if sev == "error":
        return "HIGH"
    if sev == "warning":
        return "MEDIUM"
    return "LOW"


def _diagnostic_file_paths(repo_path: str, file_path: str) -> tuple[str, str]:
    """Return (absolute_path, relative_path) for a diagnostic file path."""
    candidate = (file_path or "").strip()

    if not candidate:
        return "", ""

    if os.path.isabs(candidate):
        abs_path = os.path.normpath(candidate)
    else:
        # Prefer repository-relative resolution first.
        abs_path = os.path.normpath(os.path.join(repo_path, candidate))

        # If that doesn't point to a file, try workspace-relative absolute path.
        if not os.path.isfile(abs_path):
            abs_from_cwd = os.path.normpath(os.path.abspath(candidate))
            if os.path.isfile(abs_from_cwd):
                abs_path = abs_from_cwd

    if not os.path.isfile(abs_path):
        return "", ""

    try:
        rel_path = os.path.relpath(abs_path, repo_path)
    except ValueError:
        rel_path = os.path.basename(abs_path)

    return abs_path, rel_path.replace("\\", "/")


def _extract_syntax_tree_path(message: str) -> str:
    """Extract Roslyn SyntaxTree path from analyzer failure messages, if present."""
    if not message:
        return ""

    match = re.search(r"(?:^|\n)SyntaxTree:\s*([^\r\n]+)", message)
    if not match:
        return ""

    return match.group(1).strip()


def export_diagnostics_to_codechecker(
    diagnostics: list[dict],
    repo_path: str,
    project_id: str,
    commit_id: str,
) -> None:
    """
    Export own analyzer diagnostics to CodeChecker-compatible artifacts.

    This exports findings only for visualization. It does NOT execute CodeChecker analyzers.
    """
    if not CODECHECKER_EXPORT_ENABLED:
        return

    if not diagnostics:
        return

    repo_path = os.path.abspath(repo_path)
    output_dir = os.path.join(CODECHECKER_EXPORT_DIR, f"{project_id}_{commit_id[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    file_indexes: dict[str, int] = {}
    files: list[str] = []
    plist_diagnostics: list[dict] = []
    reports_json: list[dict] = []

    skipped_without_file = 0

    for diag in diagnostics:
        checker_name = str(diag.get("diagnostic_id") or "CMA_UNKNOWN")
        diag_title = str(diag.get("diagnostic_title") or checker_name)
        message = str(diag.get("message") or diag_title)

        line = int(diag.get("line") or 1)
        if line < 1:
            line = 1
        col = int(diag.get("character") or 1)
        if col < 1:
            col = 1

        file_path_raw = str(diag.get("file_path") or "")
        abs_path, rel_path = _diagnostic_file_paths(repo_path, file_path_raw)

        if not abs_path:
            # Analyzer failure diagnostics often carry the file in the message body.
            syntax_tree_path = _extract_syntax_tree_path(message)
            if syntax_tree_path:
                abs_path, rel_path = _diagnostic_file_paths(repo_path, syntax_tree_path)

        if not abs_path:
            skipped_without_file += 1
            continue

        if abs_path not in file_indexes:
            file_indexes[abs_path] = len(files)
            files.append(abs_path)
        file_idx = file_indexes[abs_path]

        plist_diagnostics.append(
            {
                "path": [
                    {
                        "kind": "event",
                        "location": {"line": line, "col": col, "file": file_idx},
                        "ranges": [],
                        "depth": 0,
                        "message": message,
                    }
                ],
                "description": message,
                "check_name": checker_name,
                "category": "CodeMetricsAnalyzer",
                "type": diag_title,
                "location": {"line": line, "col": col, "file": file_idx},
                "issue_context_kind": "function",
                "issue_context": str(diag.get("symbol") or ""),
            }
        )

        reports_json.append(
            {
                "file": {
                    "id": abs_path,
                    "path": rel_path,
                    "original_path": abs_path,
                },
                "line": line,
                "column": col,
                "message": message,
                "checker_name": checker_name,
                "severity": _to_codechecker_severity(diag.get("severity")),
                "analyzer_name": "custom-metrics",
                "category": "CodeMetricsAnalyzer",
                "type": diag_title,
                "review_status": "unreviewed",
                "source_code_comments": [],
                "bug_path_events": [],
                "bug_path_positions": [],
                "notes": [],
                "macro_expansions": [],
            }
        )

    if CODECHECKER_EXPORT_PLIST:
        plist_payload = {
            "files": files,
            "diagnostics": plist_diagnostics,
        }
        plist_path = os.path.join(output_dir, "custom_metrics.plist")
        with open(plist_path, "wb") as handle:
            plistlib.dump(plist_payload, handle, fmt=plistlib.FMT_XML)
        logger.info("CodeChecker plist exported to %s", plist_path)

    if CODECHECKER_EXPORT_JSON:
        json_payload = {
            "version": 1,
            "reports": reports_json,
        }
        json_path = os.path.join(output_dir, "custom_metrics.json")
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(json_payload, handle, indent=2, ensure_ascii=False)
        logger.info("CodeChecker JSON exported to %s", json_path)

    if skipped_without_file:
        logger.warning(
            "CodeChecker export skipped %d diagnostics without resolvable source files for %s_%s",
            skipped_without_file,
            project_id,
            commit_id[:8],
        )


def _parse_metric_from_message(message: str) -> tuple[str | None, float | None]:
    """Return (metric_name, numeric_value) by matching against known message patterns."""
    for metric_name, pattern in _METHOD_PATTERNS:
        m = pattern.search(message)
        if m:
            return metric_name, float(m.group(2))
    return None, None


def _parse_symbol_from_message(message: str) -> str | None:
    """Return the method / class name embedded in a diagnostic message."""
    for _, pattern in _METHOD_PATTERNS:
        m = pattern.search(message)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Running the analyzer with --output
# ---------------------------------------------------------------------------

def run_analyzers_with_output(
    repo_path: str,
    output_xml_path: str,
    solution_path: str | None = None,
    custom_build_command: str | None = None,
) -> bool:
    """
    Build the solution under *repo_path* and run CodeMetricsAnalyzer with
    ``--output <output_xml_path>``.

    Returns True on success, False on failure.
    """
    project_path = os.path.join(ANALYZER_DIR, ANALYZER_PROJECT_FILE)

    if not solution_path:
        solution_path = find_solution_file(repo_path)
    else:
        solution_path = os.path.join(repo_path, solution_path)

    if not solution_path:
        logger.error("No solution file found in %s", repo_path)
        return False

    logger.info("Running analyzers (XML output) for %s → %s", repo_path, output_xml_path)

    try:
        build_solution(repo_path, solution_path, custom_build_command)
    except subprocess.CalledProcessError as e:
        logger.warning("Build error, trying analyzers anyway: %s", e)

    os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)

    if os.path.exists(project_path):
        analyze_command = [
            "dotnet", "run", "--project", project_path,
            "analyze", solution_path,
            "--output", output_xml_path,
        ]
    else:
        bundled_dir = os.getenv("BUNDLED_ANALYZER_PATH", "/opt/CodeMetricsAnalyzer")
        dll_path = os.path.join(bundled_dir, "CodeMetricsAnalyzer.dll")
        if os.path.exists(dll_path):
            analyze_command = [
                "dotnet", dll_path,
                "analyze", solution_path,
                "--output", output_xml_path,
            ]
        else:
            analyze_command = [
                "dotnet", "run", "--project", project_path,
                "analyze", solution_path,
                "--output", output_xml_path,
            ]

    if MSBUILD_DIR and os.path.isdir(MSBUILD_DIR):
        analyze_command += ["--msbuild-path", MSBUILD_DIR]

    logger.info("Executing: %s", " ".join(analyze_command))
    result = subprocess.run(
        analyze_command,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        logger.error(
            "Analyzer failed (exit %s). Command: %s\nstdout:\n%s\nstderr:\n%s",
            result.returncode,
            " ".join(analyze_command),
            result.stdout,
            result.stderr,
        )
        return False

    logger.info("XML output written to %s", output_xml_path)
    return True


# ---------------------------------------------------------------------------
# Parsing a single XML output file
# ---------------------------------------------------------------------------

def parse_xml_output(xml_path: str) -> list[dict]:
    """
    Parse a CodeMetricsAnalyzer XML output file and return a flat list of
    per-diagnostic records enriched with symbol name and metric value.

    Each record::

        {
            "diagnostic_id":    "CMA0006",
            "diagnostic_title": "High Cyclomatic Complexity",
            "severity":         "Warning",
            "message":          "Method 'Foo' has a high cyclomatic complexity (8)",
            "symbol":           "Foo",
            "metric_name":      "cyclomatic_complexity",
            "metric_value":     8.0,
            "file_path":        "relative/path/to/File.cs",
            "line":             42,
            "character":        8,
            "project_name":     "MyProject",
            "project_file":     "path/to/MyProject.csproj",
        }
    """
    if not os.path.exists(xml_path):
        logger.warning("XML file not found: %s", xml_path)
        return []

    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        logger.error("Cannot parse XML file %s: %s", xml_path, exc)
        return []

    root = tree.getroot()
    records: list[dict] = []

    for project_el in root.findall(".//Projects/Project"):
        project_name = project_el.get("Name", "")
        project_file = project_el.get("FilePath", "")

        for diag_el in project_el.findall(".//Diagnostics/Diagnostic"):
            diag_id = diag_el.get("Id", "")
            severity = diag_el.findtext("Severity", "")
            message = diag_el.findtext("Message", "")
            file_path = diag_el.findtext("FilePath", "")

            location_el = diag_el.find("Location")
            line = int(location_el.get("Line", 0)) if location_el is not None else 0
            character = int(location_el.get("Character", 0)) if location_el is not None else 0

            # Derive a human-readable title from the Summary section if available
            title_el = root.find(f".//Summary/Diagnostic[@Id='{diag_id}']")
            diagnostic_title = title_el.get("Title", "") if title_el is not None else ""

            symbol = _parse_symbol_from_message(message)
            metric_name, metric_value = _parse_metric_from_message(message)

            records.append(
                {
                    "diagnostic_id": diag_id,
                    "diagnostic_title": diagnostic_title,
                    "severity": severity,
                    "message": message,
                    "symbol": symbol,
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "file_path": file_path,
                    "line": line,
                    "character": character,
                    "project_name": project_name,
                    "project_file": project_file,
                }
            )

    return records


# ---------------------------------------------------------------------------
# Accumulating multiple XML files
# ---------------------------------------------------------------------------

def accumulate_xml_files(xml_dir: str | None = None) -> dict:
    """
    Walk *xml_dir* (default: ``XML_OUTPUT_DIR``) and parse every ``*.xml``
    file produced by the analyzer. Apply threshold filtering and compute
    method/class counts.

    Returns a nested dict::

        {
            "<xml_filename_stem>": {
                "xml_path":    "...",
                "all_diagnostics_count": <count>,
                "filtered_diagnostics_count": <count>,
                "summary": {
                    "all": {
                        "method_count": <count>,
                        "class_count": <count>,
                    },
                    "filtered": {
                        "method_count": <count>,
                        "class_count": <count>,
                    }
                },
                "diagnostics": [ <filtered_record>, ... ]
            },
            ...
        }
    """
    search_dir = xml_dir or XML_OUTPUT_DIR
    accumulated: dict = {}

    xml_files = [
        os.path.join(dp, f)
        for dp, _, filenames in os.walk(search_dir)
        for f in filenames
        if f.endswith(".xml")
    ]

    if not xml_files:
        logger.warning("No XML files found in %s", search_dir)
        return accumulated

    logger.info("Accumulating %d XML file(s) from %s", len(xml_files), search_dir)

    for xml_path in sorted(xml_files):
        stem = os.path.splitext(os.path.basename(xml_path))[0]
        
        # Get ALL diagnostics (no filtering yet)
        all_records = parse_xml_output(xml_path)
        
        # Count total methods and classes
        total_methods, total_classes = _count_methods_and_classes(all_records)
        
        # Filter diagnostics by threshold
        filtered_records = [d for d in all_records if _passes_threshold(d)]
        
        # Count filtered methods and classes
        filtered_methods, filtered_classes = _count_methods_and_classes(filtered_records)
        
        accumulated[stem] = {
            "xml_path": xml_path,
            "all_diagnostics_count": len(all_records),
            "filtered_diagnostics_count": len(filtered_records),
            "summary": {
                "all": {
                    "method_count": total_methods,
                    "class_count": total_classes,
                },
                "filtered": {
                    "method_count": filtered_methods,
                    "class_count": filtered_classes,
                }
            },
            "diagnostics": filtered_records,
        }
        logger.info("  %s → %d all / %d filtered diagnostics", stem, len(all_records), len(filtered_records))

    return accumulated


# ---------------------------------------------------------------------------
# Thresholds Configuration
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "BumpyRoadAnalysis": {
        "BumpynessThreshold": 5
    },
    "FunctionParameterCountAnalysis": {
        "ParameterCountThreshold": 4
    },
    "LCOM5Analysis": {
        "CohesionThreshold": 0.3,
        "MinimumMethodCount": 2,
        "MinimumFieldCount": 1
    },
    "LCOM4Analysis": {
        "CohesionThreshold": 7,
        "MinimumMethodCount": 2,
        "MinimumFieldCount": 1
    },
    "MaintainabilityIndexAnalysis": {
        "MinimumMaintainabilityIndex": 65
    },
    "CyclomaticComplexityAnalysis": {
        "MaximumComplexity": 5
    },
    "ClassCouplingAnalysis": {
        "MaximumClassCoupling": 21
    }
}

def _passes_threshold(diagnostic: dict) -> bool:
    """
    Check if a diagnostic passes the configured thresholds.
    Returns True if the diagnostic should be included (i.e., it violates the threshold).
    """
    metric_name = diagnostic.get("metric_name")
    metric_value = diagnostic.get("metric_value")
    diagnostic_id = diagnostic.get("diagnostic_id")
    
    if metric_value is None or metric_name is None:
        # If we can't parse the metric, include it by default
        return True
    
    # CMA0001 - Bumpy Road Analysis
    if diagnostic_id == "CMA0001" or metric_name == "bumpy_road_score":
        threshold = THRESHOLDS["BumpyRoadAnalysis"]["BumpynessThreshold"]
        return metric_value >= threshold
    
    # CMA0002 - Function Parameter Count Analysis
    if diagnostic_id == "CMA0002" or metric_name == "parameter_count":
        threshold = THRESHOLDS["FunctionParameterCountAnalysis"]["ParameterCountThreshold"]
        return metric_value > threshold
    
    # CMA0005 - Maintainability Index Analysis
    if diagnostic_id == "CMA0005" or metric_name == "maintainability_index":
        threshold = THRESHOLDS["MaintainabilityIndexAnalysis"]["MinimumMaintainabilityIndex"]
        return metric_value < threshold
    
    # CMA0006 - Cyclomatic Complexity Analysis
    if diagnostic_id == "CMA0006" or metric_name == "cyclomatic_complexity":
        threshold = THRESHOLDS["CyclomaticComplexityAnalysis"]["MaximumComplexity"]
        return metric_value > threshold
    
    # CMA0003 - LCOM4 Analysis
    if diagnostic_id == "CMA0003" or metric_name == "lcom4_score":
        threshold = THRESHOLDS["LCOM4Analysis"]["CohesionThreshold"]
        return metric_value > threshold
    
    # CMA0004 - LCOM5 Analysis
    if diagnostic_id == "CMA0004" or metric_name == "lcom5_score":
        threshold = THRESHOLDS["LCOM5Analysis"]["CohesionThreshold"]
        return metric_value > threshold
    
    # CMA0007 - Class Coupling Analysis
    if diagnostic_id == "CMA0007" or metric_name == "class_coupling":
        threshold = THRESHOLDS["ClassCouplingAnalysis"]["MaximumClassCoupling"]
        return metric_value > threshold
    
    # If we can't determine the threshold, include it
    return True

def _count_methods_and_classes(diagnostics: list) -> tuple[int, int]:
    """
    Count unique methods and classes from the diagnostic list.
    Returns (method_count, class_count)
    """
    methods = set()
    classes = set()
    
    for diagnostic in diagnostics:
        symbol = diagnostic.get("symbol")
        if not symbol:
            continue
        
        diagnostic_id = diagnostic.get("diagnostic_id")
        
        # LCOM4 and LCOM5 are class-level diagnostics
        if diagnostic_id in ("CMA0003", "CMA0004"):
            classes.add(symbol)
        else:
            methods.add(symbol)
    
    return len(methods), len(classes)

# ---------------------------------------------------------------------------
# High-level milestone-based analysis
# ---------------------------------------------------------------------------

def analyze_milestone(milestone_keywords=None) -> dict:
    """
    Fetch milestone commits, run the analyzer with ``--output`` for each
    project/commit, and return the accumulated per-method results keyed by
    project ID with threshold filtering applied.
    """
    logger.info("Fetching commits for milestone: %s", milestone_keywords)
    commit_data = get_milestone_commits(milestone_keywords)

    results: dict = {}

    for project_id, project_data in commit_data.items():
        try:
            repo_path = clone_repo(project_id)
            commit_id = project_data.get("last_commit_id")

            if not commit_id or not repo_path:
                continue

            checkout_commit(repo_path, commit_id)

            xml_filename = f"{project_id}_{commit_id[:8]}.xml"
            xml_path = os.path.join(XML_OUTPUT_DIR, xml_filename)

            success = run_analyzers_with_output(repo_path, xml_path)

            if success:
                # Get ALL diagnostics (no threshold filtering yet)
                all_diagnostics = parse_xml_output(xml_path)

                # Export own analyzer findings for optional CodeChecker visualization.
                export_diagnostics_to_codechecker(
                    diagnostics=all_diagnostics,
                    repo_path=repo_path,
                    project_id=str(project_id),
                    commit_id=commit_id,
                )
                
                # Count total methods and classes
                total_methods, total_classes = _count_methods_and_classes(all_diagnostics)
                
                # Filter diagnostics by threshold
                filtered_diagnostics = [d for d in all_diagnostics if _passes_threshold(d)]
                
                # Count filtered methods and classes
                filtered_methods, filtered_classes = _count_methods_and_classes(filtered_diagnostics)
                
                results[project_id] = {
                    "project_id": project_id,
                    "commit_id": commit_id,
                    "xml_path": xml_path,
                    "all_diagnostics_count": len(all_diagnostics),
                    "filtered_diagnostics_count": len(filtered_diagnostics),
                    "summary": {
                        "all": {
                            "method_count": total_methods,
                            "class_count": total_classes,
                        },
                        "filtered": {
                            "method_count": filtered_methods,
                            "class_count": filtered_classes,
                        }
                    },
                    "diagnostics": filtered_diagnostics,
                }
            else:
                logger.warning("Analysis failed for project %s at commit %s", project_id, commit_id)

        except Exception as exc:
            logger.error("Error analyzing project %s: %s", project_id, exc)

    return results


def analyze_all_milestones() -> None:
    """
    Iterate over all configured milestones, run analyzer with ``--output``
    for every project/commit, then accumulate all generated XML files into
    a single ``method_analysis_results.json`` with threshold filtering applied.
    """
    for idx, milestone in enumerate(MILESTONES, start=1):
        logger.info("=== Milestone %d: %s ===", idx, milestone)
        milestone_results = analyze_milestone(milestone)

        per_milestone_file = os.path.join(
            WORKSPACE, f"method_analysis_results_{idx}.json"
        )
        with open(per_milestone_file, "w", encoding="utf-8") as fh:
            json.dump(milestone_results, fh, indent=4, ensure_ascii=False)
        logger.info("Milestone %d results written to %s", idx, per_milestone_file)

    # After all milestones, accumulate every XML file that was generated
    logger.info("Accumulating all XML outputs from %s …", XML_OUTPUT_DIR)
    accumulated = accumulate_xml_files(XML_OUTPUT_DIR)

    with open(ACCUMULATED_OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(accumulated, fh, indent=4, ensure_ascii=False)

    total_all_diagnostics = sum(v["all_diagnostics_count"] for v in accumulated.values())
    total_filtered_diagnostics = sum(v["filtered_diagnostics_count"] for v in accumulated.values())
    logger.info(
        "Accumulated %d diagnostic(s) (%d filtered) across %d XML file(s) → %s",
        total_all_diagnostics,
        total_filtered_diagnostics,
        len(accumulated),
        ACCUMULATED_OUTPUT,
    )
    print(f"✅ Method-level analysis complete. {total_all_diagnostics} total diagnostics ({total_filtered_diagnostics} filtered) accumulated → {ACCUMULATED_OUTPUT}")


if __name__ == "__main__":
    analyze_all_milestones()
