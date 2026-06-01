#!/bin/bash
# entrypoint.sh
# Merges the baked-in config.yml with environment-variable overrides, writes a
# runtime config to /tmp/runtime-config.yml, then runs the analyzer.
#
# Required (no fallback — never bake secrets into the image):
#   GITLAB_TOKEN        GitLab personal access token
#
# Optional — env var overrides the value from config.yml; if neither is set the
# default listed below is used or an error is raised:
#   GITLAB_URL          GitLab API base URL          (falls back to config.yml gitlab.url)
#   GITLAB_GROUP_ID     GitLab group ID or path      (falls back to config.yml gitlab.group_id)
#   GITLAB_SUBGROUP_ID  Subgroup filter              (falls back to config.yml gitlab.subgroup_id)
#
# Milestones — env var overrides config.yml; choose one format:
#   MILESTONE_KEYWORDS  JSON array-of-arrays: '[["Name","Alt"],["Name2"]]'
#   OR numbered vars:   MILESTONE_1="Name,Alt name"   MILESTONE_2="Name2,Alt2"
#   Falls back to config.yml gitlab.milestone_keywords when neither is provided.
#
# Note: Unity projects are handled automatically using a pure-Python solution
#       generator — no Unity editor or license is required.
#
# Other:
#   CLONE_DIR           Where to clone repos         (falls back to config.yml project.clone_dir)
#   REPORT_OUTPUT       Output directory             (default: /app/reports)
#   PROCESSED_COMMITS_PATH  Persist skip-list across runs

set -euo pipefail

# ── GITLAB_TOKEN is the only hard requirement ─────────────────────────────────
if [ -z "${GITLAB_TOKEN:-}" ]; then
    echo "[ERROR] GITLAB_TOKEN is required but not set." >&2
    echo "        Pass it with: -e GITLAB_TOKEN=glpat-..." >&2
    exit 1
fi

# ── Set up log file in the reports directory ──────────────────────────────────
REPORT_OUTPUT="${REPORT_OUTPUT:-/app/reports}"
mkdir -p "${REPORT_OUTPUT}"
LOG_FILE="${REPORT_OUTPUT}/run_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "${LOG_FILE}") 2>&1
echo "[INFO]  Log file      : ${LOG_FILE}"

# Optional: Unity license file path (mount file into container and set this env var)
if [ -n "${UNITY_LICENSE_PATH:-}" ]; then
    if [ -f "${UNITY_LICENSE_PATH}" ]; then
        echo "[INFO]  Unity license : ${UNITY_LICENSE_PATH}"
        export UNITY_LICENSE_PATH
    else
        echo "[WARN]  UNITY_LICENSE_PATH is set but file not found: ${UNITY_LICENSE_PATH}"
    fi
fi

# ── Generate runtime config by merging config.yml + env vars ─────────────────
python3 - <<'PYEOF'
import json, os, sys, yaml

BASE_CONFIG   = "/opt/bulk_analyzer/config.yml"
config_file   = os.environ.get("ANALYZER_CONFIG", "/tmp/runtime-config.yml")

# ── Load the baked-in config as the starting point ────────────────────────
base = {}
if os.path.isfile(BASE_CONFIG):
    with open(BASE_CONFIG, "r", encoding="utf-8") as fh:
        base = yaml.safe_load(fh) or {}

base_gitlab   = base.get("gitlab",   {}) or {}
base_project  = base.get("project",  {}) or {}
base_analyzer = base.get("analyzer", {}) or {}

# ── GitLab settings ────────────────────────────────────────────────────────
gitlab_url = (os.environ.get("GITLAB_URL", "") or "").strip() or base_gitlab.get("url", "")
if not gitlab_url:
    print("[ERROR] GITLAB_URL not set and not found in config.yml.", file=sys.stderr)
    sys.exit(1)

# Token comes only from the environment — never from config.yml
gitlab_token = os.environ["GITLAB_TOKEN"]

group_id = (os.environ.get("GITLAB_GROUP_ID", "") or "").strip() or str(base_gitlab.get("group_id", ""))
if not group_id:
    print("[ERROR] GITLAB_GROUP_ID not set and not found in config.yml.", file=sys.stderr)
    sys.exit(1)

subgroup_id = (os.environ.get("GITLAB_SUBGROUP_ID", "") or "").strip() or str(base_gitlab.get("subgroup_id", "") or "")

# ── Milestones ─────────────────────────────────────────────────────────────
milestone_keywords_json = (os.environ.get("MILESTONE_KEYWORDS", "") or "").strip()

if milestone_keywords_json:
    try:
        milestone_keywords = json.loads(milestone_keywords_json)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] MILESTONE_KEYWORDS is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(milestone_keywords, list) or not all(isinstance(m, list) for m in milestone_keywords):
        print('[ERROR] MILESTONE_KEYWORDS must be a JSON array of arrays, e.g.\n'
              '        \'[["Milestone 1","Alt 1"],["Milestone 2","Alt 2"]]\'', file=sys.stderr)
        sys.exit(1)
else:
    # Try numbered MILESTONE_1, MILESTONE_2, ...
    milestone_keywords = []
    i = 1
    while True:
        val = (os.environ.get(f"MILESTONE_{i}", "") or "").strip()
        if not val:
            break
        milestone_keywords.append([s.strip() for s in val.split(",")])
        i += 1

    if not milestone_keywords:
        # Fall back to whatever is in config.yml
        milestone_keywords = base_gitlab.get("milestone_keywords", []) or []

if not milestone_keywords:
    print("[ERROR] No milestones configured.\n"
          "        Set MILESTONE_KEYWORDS (JSON), MILESTONE_1/MILESTONE_2/... env vars,\n"
          "        or provide a config.yml with gitlab.milestone_keywords.", file=sys.stderr)
    sys.exit(1)

# ── Clone directory ────────────────────────────────────────────────────────
clone_dir = (os.environ.get("CLONE_DIR", "") or "").strip() or base_project.get("clone_dir", "/tmp/repos")

# ── Assemble merged config ─────────────────────────────────────────────────
config = {
    "gitlab": {
        "url":                gitlab_url,
        "token":              gitlab_token,
        "group_id":           group_id,
        "milestone_keywords": milestone_keywords,
    },
    "project": {
        "clone_dir": clone_dir,
    },
    "public_analyzer": base.get("public_analyzer", {
        "repository_list": "repos.json",
        "clone_dir":       "/tmp/public_repos",
        "concurrency":     6,
    }),
    "analyzer": {
        "solution_dir":  base_analyzer.get("solution_dir",  ""),
        "project_dir":   base_analyzer.get("project_dir",   ""),
        "msbuild_dir":   base_analyzer.get("msbuild_dir",   ""),
        "project_file":  base_analyzer.get("project_file",  "CodeMetricsAnalyzer.csproj"),
    },
    "docker": base.get("docker", {"image": "code-metrics-analyzer"}),
}

if subgroup_id:
    config["gitlab"]["subgroup_id"] = subgroup_id

os.makedirs(os.path.dirname(config_file) or ".", exist_ok=True)
with open(config_file, "w", encoding="utf-8") as fh:
    yaml.dump(config, fh, default_flow_style=False, allow_unicode=True)

# ── Summary (token intentionally omitted) ─────────────────────────────────
src = "(config.yml)" if os.path.isfile(BASE_CONFIG) else ""
print(f"[INFO]  GitLab URL    : {gitlab_url}")
print(f"[INFO]  Group ID      : {group_id}")
if subgroup_id:
    print(f"[INFO]  Subgroup ID   : {subgroup_id}")
print(f"[INFO]  Milestones    : {len(milestone_keywords)}")
for i, ms in enumerate(milestone_keywords, 1):
    alts = f" (+ {len(ms)-1} alt name{'s' if len(ms)-1 != 1 else ''})" if len(ms) > 1 else ""
    print(f"[INFO]    {i}. {ms[0]}{alts}")
PYEOF

export ANALYZER_CONFIG="${ANALYZER_CONFIG:-/tmp/runtime-config.yml}"
export CONFIG_PATH="$ANALYZER_CONFIG"

# ── Run analyzer ──────────────────────────────────────────────────────────────
exec python3 -m bulk_analyzer.analyzer "$@"
