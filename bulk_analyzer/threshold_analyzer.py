import json
import os
import shutil
import yaml
from milestone_commit_finder import get_projects, get_subgroups
from analyzer import clone_repo
from method_analyzer import run_analyzers_with_output, parse_xml_output

# === Load Configuration ===
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)

# === Configuration ===
GROUP_ID = config["gitlab"]["group_id"] + ("%2f" + config["gitlab"]["subgroup_id"] if config["gitlab"]["subgroup_id"] else "")
ANALYZER_DIR = config["analyzer"]["project_dir"]
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(WORKSPACE_DIR, "threshold_analysis_results.json")
XML_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "threshold_xml_outputs")

# Threshold ranges for each metric
THRESHOLD_RANGES = {
    "bumpy": [i / 10 for i in range(0, 101)],          # 0.0 .. 10.0
    "fpc": list(range(0, 11)),                         # 0 .. 10
    "lcom5": [i / 100 for i in range(0, 101)],         # 0.00 .. 1.00
    "lcom4": list(range(1, 11)),                       # 1 .. 10
    "mi": list(range(0, 101, 5)),                      # 0 .. 100
    "cc": list(range(1, 31)),                          # 1 .. 30
    "coupling": list(range(1, 31)),                    # 1 .. 30
}

METRIC_NAME_MAP = {
    "bumpy_road_score": "bumpy",
    "parameter_count": "fpc",
    "lcom5_score": "lcom5",
    "lcom4_score": "lcom4",
    "maintainability_index": "mi",
    "cyclomatic_complexity": "cc",
    "class_coupling": "coupling",
}

def get_all_projects():
    """Get all projects."""
    subgroup_ids = get_subgroups(GROUP_ID)
    if not subgroup_ids:
        subgroup_ids.append(GROUP_ID)

    projects = []

    for subgroup_id in subgroup_ids:
        print(f"Get projects for {subgroup_id}...")
        # Get projects inside this subgroup and its direct subgroups
        projects += get_projects(subgroup_id)

    return projects


def backup_config():
    """Backup the current appsettings.json"""
    config_path = os.path.join(ANALYZER_DIR, "appsettings.json")
    backup_path = os.path.join(ANALYZER_DIR, "appsettings.json.backup")
    
    if not os.path.exists(config_path):
        return None

    shutil.copy2(config_path, backup_path)
    print(f"✅ Backed up config to {backup_path}")
    return backup_path


def restore_config(backup_path):
    """Restore the original appsettings.json"""
    config_path = os.path.join(ANALYZER_DIR, "appsettings.json")
    
    if backup_path and os.path.exists(backup_path):
        shutil.copy2(backup_path, config_path)
        os.remove(backup_path)
        print(f"✅ Restored config from backup")


def update_config_extreme():
    """Update the JSON config file to report ALL metrics (extreme thresholds)."""
    config_path = os.path.join(ANALYZER_DIR, "appsettings.json")
    with open(config_path, "r", encoding="utf8") as f:
        conf = json.load(f)

    # Set thresholds so analyzer emits as many diagnostics as possible in one run.
    # For metrics reported on "value > threshold", we use 0.
    # For maintainability ("value < threshold"), we use >100.
    conf["BumpyRoadAnalysis"]["BumpynessThreshold"] = 0
    conf["FunctionParameterCountAnalysis"]["ParameterCountThreshold"] = 0
    conf["LCOM5Analysis"]["CohesionThreshold"] = 0.0
    conf["LCOM4Analysis"]["CohesionThreshold"] = 0
    conf["MaintainabilityIndexAnalysis"]["MinimumMaintainabilityIndex"] = 101
    conf["CyclomaticComplexityAnalysis"]["MaximumComplexity"] = 0
    conf["ClassCouplingAnalysis"]["MaximumClassCoupling"] = 0

    with open(config_path, "w", encoding="utf8") as f:
        json.dump(conf, f, indent=4)
    
    print("✅ Updated config to extreme thresholds")


def collect_metric_values(projects: list[str]) -> dict:
    """
    Run analyzer once per project with XML output and collect raw metric values
    from diagnostics.
    """
    os.makedirs(XML_OUTPUT_DIR, exist_ok=True)

    metric_values = {k: [] for k in THRESHOLD_RANGES.keys()}

    for project in projects:
        print(f"🔍 Analyzing {project}...")
        repo_path = clone_repo(project)
        if not repo_path:
            continue

        xml_path = os.path.join(XML_OUTPUT_DIR, f"{project}.xml")
        ok = run_analyzers_with_output(repo_path=repo_path, output_xml_path=xml_path)
        if not ok:
            print(f"⚠ Analyzer failed for project {project}")
            continue

        records = parse_xml_output(xml_path)
        for rec in records:
            source_name = rec.get("metric_name")
            mapped_name = METRIC_NAME_MAP.get(source_name)
            value = rec.get("metric_value")
            if mapped_name is None or value is None:
                continue

            metric_values[mapped_name].append(float(value))

    return metric_values


def aggregate_metrics_by_thresholds(metric_values: dict) -> dict:
    """
    Count diagnostics per threshold using raw diagnostic metric values.
    """
    result = {k: {} for k in THRESHOLD_RANGES.keys()}

    for metric_key, thresholds in THRESHOLD_RANGES.items():
        values = metric_values.get(metric_key, [])
        for threshold in thresholds:
            if metric_key == "bumpy":
                count = sum(1 for v in values if v >= threshold)
            elif metric_key == "fpc":
                count = sum(1 for v in values if v > threshold)
            elif metric_key == "lcom5":
                count = sum(1 for v in values if v > threshold)
            elif metric_key == "lcom4":
                count = sum(1 for v in values if v > threshold)
            elif metric_key == "mi":
                count = sum(1 for v in values if v < threshold)
            elif metric_key == "cc":
                count = sum(1 for v in values if v > threshold)
            else:  # coupling
                count = sum(1 for v in values if v > (10 + threshold))

            # JSON object keys are strings; keep it explicit.
            result[metric_key][str(threshold)] = count

    return result


def analyze_projects():
    """Run analyzer once per project and export one aggregated threshold file."""
    # Backup original config
    backup_path = backup_config()
    
    try:
        # Update config to extreme thresholds
        update_config_extreme()
        
        projects = get_all_projects()
        metric_values = collect_metric_values(projects)

        # Aggregate metrics across all thresholds
        print(f"📊 Aggregating metrics across all thresholds...")
        aggregated = aggregate_metrics_by_thresholds(metric_values)

        # Save single results file
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(aggregated, f, indent=4)

        print(f"✅ Saved aggregated results to {OUTPUT_FILE}")
        print(f"   Metrics: {list(aggregated.keys())}")
    
    finally:
        # Restore original config
        restore_config(backup_path)


if __name__ == "__main__":
    analyze_projects()