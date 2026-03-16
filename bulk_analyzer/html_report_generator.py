"""
bulk_analyzer/html_report_generator.py

Generate an interactive HTML report for bulk analyzer JSON outputs.

Features
--------
* Overview sunburst – all projects as sectors sized by total issue count,
  outer ring breaks each project into its constituent issue types (aggregated
  across every milestone).
* Detail panel – appears when a project sector is clicked; shows:
    - per-milestone issue counts and commit references
    - a second sunburst: Milestone → Issue Type → Severity
    - a persistence table: rows = unique issue types, columns = milestones
      with colour-coded cells (new / persists / resolved / absent)

Usage
-----
    python -m bulk_analyzer.html_report_generator
    python -m bulk_analyzer.html_report_generator \\
        --inputs method_analysis_results_1.json method_analysis_results_2.json \\
        --output reports/bulk-report.html
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from html import escape as he
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).resolve().parent.parent

DEFAULT_INPUT_PATTERNS = [
    "method_analysis_results_?.json",
    "method_analysis_results_??.json",
    "analysis_results_?.json",
    "analysis_results_??.json",
    "public_analysis_results.json",
]
DEFAULT_OUTPUT = WORKSPACE / "bulk_analysis_report.html"

METRIC_FIELD_METADATA: dict[str, dict[str, str]] = {
    "bumpy_score": {
        "diagnostic_id": "CMA0001",
        "diagnostic_title": "Bumpy Road Code Smell",
        "severity": "Warning",
    },
    "fpc_score": {
        "diagnostic_id": "CMA0002",
        "diagnostic_title": "High Function Parameter Count",
        "severity": "Warning",
    },
    "lcom4_score": {
        "diagnostic_id": "CMA0003",
        "diagnostic_title": "Lack of Cohesion of Methods (LCOM4)",
        "severity": "Warning",
    },
    "lcom5_score": {
        "diagnostic_id": "CMA0004",
        "diagnostic_title": "Lack of Cohesion of Methods (LCOM5)",
        "severity": "Warning",
    },
    "maintainability_index_score": {
        "diagnostic_id": "CMA0005",
        "diagnostic_title": "Low Maintainability Index",
        "severity": "Warning",
    },
    "cyclomatic_complexity_score": {
        "diagnostic_id": "CMA0006",
        "diagnostic_title": "High Cyclomatic Complexity",
        "severity": "Warning",
    },
    "class_coupling_score": {
        "diagnostic_id": "CMA0007",
        "diagnostic_title": "High Class Coupling",
        "severity": "Warning",
    },
}

DIAGNOSTIC_TITLES: dict[str, str] = {
    v["diagnostic_id"]: v["diagnostic_title"] for v in METRIC_FIELD_METADATA.values()
}

METRIC_VALUE_PATTERN = re.compile(r"\(([-+]?\d+[\d.,]*)\)")
SYMBOL_PATTERN = re.compile(r"(?:Method|Class) '([^']+)'|'([^']+)' has")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an interactive HTML report for bulk analyzer JSON outputs."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=DEFAULT_INPUT_PATTERNS,
        help="Input files or glob patterns (relative to workspace root).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output HTML file path.",
    )
    parser.add_argument(
        "--title",
        default="Bulk Analyzer \u2014 Milestone Comparison",
        help="Report title.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Input discovery
# ---------------------------------------------------------------------------


def resolve_input_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        candidate = Path(pattern)
        has_glob = any(ch in pattern for ch in "*?[]")
        if has_glob:
            base = candidate.parent if candidate.is_absolute() else WORKSPACE
            name_glob = candidate.name if candidate.is_absolute() else pattern
            if candidate.is_absolute():
                matches_iter = base.glob(name_glob)
            else:
                matches_iter = WORKSPACE.glob(pattern)
            matches = sorted(Path(p).resolve() for p in matches_iter if Path(p).exists())
        else:
            resolved = candidate if candidate.is_absolute() else WORKSPACE / candidate
            matches = [resolved.resolve()] if resolved.exists() else []
        for match in matches:
            if match not in seen:
                seen.add(match)
                files.append(match)
    return files


def source_label_for(path: Path) -> str:
    stem = path.stem
    m = re.search(r"(?:method_)?analysis_results_(\d+)$", stem)
    if m:
        return f"Milestone {m.group(1)}"
    if stem == "public_analysis_results":
        return "Public analysis"
    if stem == "method_analysis_results":
        return "Accumulated results"
    return stem.replace("_", " ").strip().title()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _parse_metric_value(value: Any, message: str | None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(message, str):
        m = METRIC_VALUE_PATTERN.search(message)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                pass
    return None


def _parse_symbol(symbol: Any, message: str | None) -> str | None:
    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip()
    if isinstance(message, str):
        m = SYMBOL_PATTERN.search(message)
        if m:
            return (m.group(1) or m.group(2) or "").strip() or None
    return None


def _make_ref_label(record: dict[str, Any]) -> str:
    for key in ("tag", "commit_id", "commit", "ref"):
        v = record.get(key)
        if isinstance(v, str) and v.strip():
            v = v.strip()
            if key == "commit_id" and len(v) > 8:
                return v[:8]
            return v
    return "\u2014"


def _project_name(record_key: str, record: dict[str, Any], diagnostics: list[dict]) -> str:
    # Prefer the numeric project_id / record key as the student-project label.
    # This keeps project 989, 992, 993, 996 distinct and easy to find.
    pid = record.get("project_id")
    if pid not in (None, ""):
        return f"Project {pid}"
    # If the key itself looks like an ID (digits), use it.
    key_str = str(record_key).strip()
    if key_str.isdigit():
        return f"Project {key_str}"
    # For public-analysis / other formats that carry an explicit name, use it.
    for k in ("project_name", "name"):
        v = record.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return key_str


def _normalise_detail_diag(raw: dict[str, Any], source_label: str) -> dict[str, Any]:
    did = str(raw.get("diagnostic_id") or "Unknown")
    title = raw.get("diagnostic_title") or DIAGNOSTIC_TITLES.get(did, did)
    message = raw.get("message") or str(title)
    return {
        "diagnostic_id": did,
        "diagnostic_title": str(title),
        "severity": str(raw.get("severity") or "Warning"),
        "count": 1,
        "message": str(message),
        "file_path": str(raw.get("file_path") or ""),
        "line": int(raw.get("line") or 0),
        "symbol": _parse_symbol(raw.get("symbol"), message),
        "metric_value": _parse_metric_value(raw.get("metric_value"), message),
        "project_name": str(raw.get("project_name") or ""),
        "source_label": source_label,
    }


def _normalise_summary_diag(
    metric_field: str, count: Any, source_label: str, project_name: str, ref_label: str
) -> dict[str, Any] | None:
    meta = METRIC_FIELD_METADATA.get(metric_field)
    if meta is None:
        return None
    try:
        total = int(count or 0)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    return {
        "diagnostic_id": meta["diagnostic_id"],
        "diagnostic_title": meta["diagnostic_title"],
        "severity": meta["severity"],
        "count": total,
        "message": f"{total} finding(s) ({meta['diagnostic_title']})",
        "file_path": "",
        "line": 0,
        "symbol": project_name,
        "metric_value": float(total),
        "project_name": project_name,
        "source_label": source_label,
    }


# ---------------------------------------------------------------------------
# Load & normalise entries from a single file
# ---------------------------------------------------------------------------


def _load_detail_record(key: str, record: dict, source_label: str, path: Path) -> dict | None:
    diags = [
        _normalise_detail_diag(d, source_label)
        for d in record.get("diagnostics", [])
        if isinstance(d, dict)
    ]
    pname = _project_name(key, record, diags)
    if not diags:
        return None
    # Collect the internal csproj names for the detail view
    sub_names = sorted({d["project_name"] for d in diags if d["project_name"]})
    return {
        "source_label": source_label,
        "input_file": str(path),
        "project_key": str(key),
        "project_name": pname,
        "sub_project_names": sub_names,
        "ref_label": _make_ref_label(record),
        "diagnostics": diags,
    }


def _load_summary_record(
    key: str, record: dict, source_label: str, path: Path, ref_fallback: str = "\u2014"
) -> dict | None:
    ref = _make_ref_label(record)
    if ref == "\u2014":
        ref = ref_fallback
    pname = str(record.get("project_name") or record.get("project_id") or key)
    diags = [
        d
        for field in METRIC_FIELD_METADATA
        for d in [_normalise_summary_diag(field, record.get(field), source_label, pname, ref)]
        if d is not None
    ]
    if not diags:
        return None
    return {
        "source_label": source_label,
        "input_file": str(path),
        "project_key": str(key),
        "project_name": pname,
        "ref_label": ref,
        "diagnostics": diags,
    }


def load_entries_from_file(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        return []

    source_label = source_label_for(path)
    entries: list[dict] = []

    for key, value in payload.items():
        if not isinstance(value, dict):
            continue

        if isinstance(value.get("diagnostics"), list):
            e = _load_detail_record(str(key), value, source_label, path)
            if e:
                entries.append(e)
            continue

        if any(f in value for f in METRIC_FIELD_METADATA):
            e = _load_summary_record(str(key), value, source_label, path)
            if e:
                entries.append(e)
            continue

        # Nested dict (public_analysis_results: project → {ref_idx → record})
        for child_key, child in sorted(value.items(), key=lambda x: str(x[0])):
            if isinstance(child, dict) and any(f in child for f in METRIC_FIELD_METADATA):
                e = _load_summary_record(
                    str(key), child, source_label, path, ref_fallback=str(child_key)
                )
                if e:
                    entries.append(e)

    return entries


# ---------------------------------------------------------------------------
# Comparison data model
# ---------------------------------------------------------------------------


def _ordered_milestones(entries: list[dict]) -> list[str]:
    seen: list[str] = []
    for e in entries:
        lbl = e["source_label"]
        if lbl not in seen:
            seen.append(lbl)

    def _sort_key(lbl: str) -> tuple:
        m = re.search(r"(\d+)", lbl)
        return (int(m.group(1)) if m else 9999, lbl)

    return sorted(seen, key=_sort_key)


def _diag_weight(d: dict) -> int:
    return max(int(d.get("count") or 1), 1)


def build_comparison_data(entries: list[dict]) -> dict[str, Any]:
    """
    Returns a dict with:
      milestone_order  – ordered list of milestone labels
      projects_meta    – [{key, name, total}, ...]  sorted by total desc
      overview_sunburst – D3 tree: All Projects -> Project -> Issue Type
      per_project      – {key: {name, total, milestones, detail_sunburst,
                                persistence_rows, all_diag_ids}}
    """
    milestone_order = _ordered_milestones(entries)

    by_project: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    project_names: dict[str, str] = {}
    ref_labels: dict[str, dict[str, str]] = defaultdict(dict)

    for entry in entries:
        pkey = entry["project_key"]
        project_names.setdefault(pkey, entry["project_name"])
        by_project[pkey][entry["source_label"]].extend(entry["diagnostics"])
        ref_labels[pkey].setdefault(entry["source_label"], entry["ref_label"])

    per_project: dict[str, Any] = {}

    # Collect sub-project names per (pkey, milestone)
    sub_names_map: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for entry in entries:
        pkey = entry["project_key"]
        lbl = entry["source_label"]
        subs = entry.get("sub_project_names", [])
        existing = sub_names_map[pkey].get(lbl, [])
        merged = sorted(set(existing) | set(subs))
        sub_names_map[pkey][lbl] = merged

    for pkey, by_milestone in sorted(by_project.items()):
        pname = project_names.get(pkey, pkey)
        grand_total = 0
        milestones_data: dict[str, Any] = {}

        for milestone_label, diags in by_milestone.items():
            issue_types: dict[str, dict] = {}
            for d in diags:
                did = d["diagnostic_id"]
                w = _diag_weight(d)
                grand_total += w
                if did not in issue_types:
                    issue_types[did] = {
                        "title": d["diagnostic_title"],
                        "severity": d["severity"],
                        "count": 0,
                    }
                issue_types[did]["count"] += w

            milestones_data[milestone_label] = {
                "ref_label": ref_labels[pkey].get(milestone_label, "\u2014"),
                "total": sum(v["count"] for v in issue_types.values()),
                "issue_types": issue_types,
                "sub_project_names": sub_names_map[pkey].get(milestone_label, []),
            }

        all_diag_ids: list[str] = sorted(
            {did for ms in milestones_data.values() for did in ms["issue_types"]}
        )

        diag_title_map: dict[str, str] = {}
        for ms in milestones_data.values():
            for did, info in ms["issue_types"].items():
                diag_title_map.setdefault(did, info["title"])

        persistence_rows: list[dict] = []
        for did in all_diag_ids:
            by_ms: dict[str, int] = {
                lbl: (milestones_data[lbl]["issue_types"].get(did, {}).get("count", 0)
                      if lbl in milestones_data else 0)
                for lbl in milestone_order
            }
            persistence_rows.append({
                "diag_id": did,
                "title": diag_title_map.get(did, did),
                "by_milestone": by_ms,
            })

        # Symbol-level data: diag_id -> {sym_key -> {symbol, sub_project, file, by_milestone}}
        # Built first so the detail sunburst can use symbols as its leaf ring.
        sym_compare: dict[str, dict[str, Any]] = defaultdict(dict)
        for milestone_label, diags in by_milestone.items():
            for d in diags:
                did = d["diagnostic_id"]
                sym = d.get("symbol") or "?"
                sub_proj = d.get("project_name") or ""
                sym_key = f"{sub_proj}::{sym}"
                file_short = _short_file(d.get("file_path", ""), pkey)
                if sym_key not in sym_compare[did]:
                    sym_compare[did][sym_key] = {
                        "symbol": sym,
                        "sub_project": sub_proj,
                        "file": file_short,
                        "by_milestone": {},
                    }
                # Keep the entry with the lowest line number per milestone (dedup same sym/ms)
                existing = sym_compare[did][sym_key]["by_milestone"].get(milestone_label)
                line = int(d.get("line") or 0)
                val = d.get("metric_value")
                if existing is None or (line > 0 and line < existing["line"]):
                    sym_compare[did][sym_key]["by_milestone"][milestone_label] = {
                        "line": line,
                        "value": round(val, 2) if isinstance(val, float) else val,
                    }

        symbol_comparison: dict[str, list[dict]] = {}
        for did in all_diag_ids:
            rows_sym = sorted(
                sym_compare[did].values(),
                key=lambda r: (r["sub_project"], r["symbol"]),
            )
            if rows_sym:
                symbol_comparison[did] = rows_sym

        # Detail sunburst: Milestone -> Issue Type
        detail_root: dict[str, Any] = {"name": pname, "children": []}
        for lbl in milestone_order:
            ms = milestones_data.get(lbl)
            if ms is None:
                continue
            ms_node: dict[str, Any] = {"name": lbl, "children": []}
            for did, info in sorted(ms["issue_types"].items(), key=lambda x: -x[1]["count"]):
                ms_node["children"].append({
                    "name": did,
                    "title": info["title"],
              "value": info["count"],
                })
            if ms_node["children"]:
                detail_root["children"].append(ms_node)

        per_project[pkey] = {
            "name": pname,
            "total": grand_total,
            "milestones": milestones_data,
            "detail_sunburst": detail_root,
            "persistence_rows": persistence_rows,
            "all_diag_ids": all_diag_ids,
            "symbol_comparison": symbol_comparison,
        }

    # Overview sunburst: All Projects -> Project -> Issue Type (totals across milestones)
    overview_root: dict[str, Any] = {"name": "All Projects", "children": []}
    for pkey, pdata in sorted(per_project.items(), key=lambda x: -x[1]["total"]):
        consolidated: Counter[str] = Counter()
        for ms in pdata["milestones"].values():
            for did, info in ms["issue_types"].items():
                consolidated[did] += info["count"]
        project_node: dict[str, Any] = {
            "name": pdata["name"],
            "key": pkey,
            "children": [
                {"name": did, "value": count}
                for did, count in sorted(consolidated.items(), key=lambda x: -x[1])
            ],
        }
        if project_node["children"]:
            overview_root["children"].append(project_node)

    projects_meta = [
        {"key": pkey, "name": pdata["name"], "total": pdata["total"]}
        for pkey, pdata in sorted(per_project.items(), key=lambda x: -x[1]["total"])
    ]

    return {
        "milestone_order": milestone_order,
        "projects_meta": projects_meta,
        "overview_sunburst": overview_root,
        "per_project": per_project,
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------


def _relative(path: str) -> str:
    if not path:
        return "\u2014"
    try:
        return str(Path(path).resolve().relative_to(WORKSPACE)).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def _short_file(path: str, project_key: str) -> str:
    """Return file path relative to the student-project root (strips absolute prefix)."""
    if not path:
        return ""
    p = path.replace("\\", "/")
    marker = f"/repos/{project_key}/"
    idx = p.find(marker)
    if idx >= 0:
        return p[idx + len(marker):]
    # Fallback: last 3 path components
    parts = p.split("/")
    return "/".join(parts[-3:]) if len(parts) >= 3 else p


def render_report(entries: list[dict], input_files: list[Path], title: str) -> str:
    cdata = build_comparison_data(entries)
    milestone_order = cdata["milestone_order"]
    projects_meta = cdata["projects_meta"]
    per_project = cdata["per_project"]
    total_issues = sum(p["total"] for p in per_project.values())
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    input_labels = ", ".join(_relative(str(p)) for p in input_files)

    projects_list_html = "".join(
        f'<li class="project-item" data-key="{he(p["key"])}" '
        f'title="{he(p["name"])} \u2013 {p["total"]} issues">'
        f'<span class="project-pill">{he(p["name"])}</span>'
        f'<span class="project-count">{p["total"]}</span>'
        f"</li>"
        for p in projects_meta
    )

    overview_js = json.dumps(cdata["overview_sunburst"], ensure_ascii=False)
    per_project_js = json.dumps(
        {
            pkey: {
                "name": pd["name"],
                "total": pd["total"],
                "milestones": pd["milestones"],
                "detail_sunburst": pd["detail_sunburst"],
                "persistence_rows": pd["persistence_rows"],
                "all_diag_ids": pd["all_diag_ids"],                "symbol_comparison": pd["symbol_comparison"],            }
            for pkey, pd in per_project.items()
        },
        ensure_ascii=False,
    )
    milestone_order_js = json.dumps(milestone_order, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{he(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    :root {{
      --bg:#0a0f1e; --panel:#111827; --soft:#1a2236; --border:rgba(148,163,184,.18);
      --text:#e5e7eb; --muted:#8898aa; --accent:#38bdf8; --glow:rgba(56,189,248,.14);
      --c-new:#f59e0b; --c-persists:#ef4444; --c-resolved:#22c55e; --c-only:#60a5fa;
      --transition:220ms cubic-bezier(.4,0,.2,1);
    }}
    *{{box-sizing:border-box;margin:0;padding:0}}
    html{{scroll-behavior:smooth}}
    body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}
    /* layout */
    .page{{max-width:1560px;margin:0 auto;padding:26px 18px 60px}}
    .hero{{background:radial-gradient(circle at top left,rgba(56,189,248,.18),transparent 50%),var(--panel);
      border:1px solid var(--border);border-radius:20px;padding:22px 26px;margin-bottom:18px}}
    .hero h1{{font-size:1.7rem;margin-bottom:5px}}
    .hero .meta{{color:var(--muted);font-size:.88rem}}
    .cards{{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}}
    .card{{background:var(--soft);border:1px solid var(--border);border-radius:14px;padding:14px 20px;min-width:130px}}
    .card-value{{font-size:1.85rem;font-weight:700}}
    .card-label{{color:var(--muted);font-size:.83rem;margin-top:3px}}
    /* workspace */
    .workspace{{display:grid;grid-template-columns:270px 1fr;gap:14px;align-items:start}}
    .sidebar{{background:var(--panel);border:1px solid var(--border);border-radius:18px;padding:14px;
      position:sticky;top:14px;max-height:90vh;overflow:hidden;display:flex;flex-direction:column}}
    .sidebar h3{{font-size:.76rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:10px}}
    .project-list{{list-style:none;display:flex;flex-direction:column;gap:5px;overflow-y:auto;flex:1}}
    .project-item{{display:flex;align-items:center;justify-content:space-between;gap:8px;
      padding:9px 11px;border-radius:10px;cursor:pointer;border:1px solid transparent;
      transition:background var(--transition),border-color var(--transition)}}
    .project-item:hover{{background:var(--soft);border-color:var(--border)}}
    .project-item.active{{background:var(--glow);border-color:var(--accent)}}
    .project-pill{{font-size:.9rem;font-weight:500}}
    .project-count{{font-size:.8rem;color:var(--muted);flex-shrink:0}}
    /* main */
    .main-pane{{display:flex;flex-direction:column;gap:14px}}
    .pane{{background:var(--panel);border:1px solid var(--border);border-radius:18px;padding:20px 22px}}
    .pane h2{{font-size:1.1rem;margin-bottom:4px}}
    .pane .sub{{color:var(--muted);font-size:.86rem;margin-bottom:14px}}
    /* sunburst row */
    .sunburst-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}  /* 3-column for overview, detail, symbol-metrics */
    .sb-box{{display:flex;flex-direction:column;align-items:center;background:var(--soft);
      border:1px solid var(--border);border-radius:14px;padding:14px 8px}}
    .sb-box#symbolSB{{min-height:380px}}  /* ensure room for metrics diagram */
    .sb-box h3{{font-size:.88rem;color:var(--muted);margin-bottom:8px}}
    .sb-center{{margin-top:8px;text-align:center}}
    .sb-center strong{{display:block;font-size:1rem}}
    .sb-center span{{color:var(--muted);font-size:.83rem}}
    svg.sb{{max-width:100%;height:auto}}
    /* placeholder */
    #detailPlaceholder{{display:flex;flex-direction:column;align-items:center;justify-content:center;
      min-height:340px;color:var(--muted);text-align:center;gap:12px}}
    #detailPlaceholder .icon{{font-size:3rem;opacity:.3}}
    /* milestone badges */
    .ms-badges{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}}
    .ms-badge{{background:var(--soft);border:1px solid var(--border);border-radius:12px;padding:10px 16px}}
    .ms-badge .ms-name{{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:3px}}
    .ms-badge .ms-count{{font-size:1.45rem;font-weight:700}}
    .ms-badge .ms-ref{{font-size:.75rem;color:var(--muted);margin-top:1px;font-family:monospace}}
    .ms-subs{{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}}
    .sub-tag{{font-size:.72rem;background:rgba(56,189,248,.10);color:var(--accent);border:1px solid rgba(56,189,248,.22);border-radius:5px;padding:2px 6px}}
    /* table */
    .tbl-wrap{{overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;font-size:.88rem}}
    th,td{{padding:9px 11px;border-bottom:1px solid var(--border);text-align:left;vertical-align:middle}}
    th{{background:rgba(10,15,30,.97);position:sticky;top:0;z-index:1;
      font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
    tbody tr:hover{{background:rgba(148,163,184,.06)}}
    td.absent{{color:var(--muted);text-align:center}}
    td.new-issue{{background:rgba(245,158,11,.13);color:var(--c-new);text-align:center;font-weight:700;border-radius:7px}}
    td.persists{{background:rgba(239,68,68,.11);color:var(--c-persists);text-align:center;font-weight:700;border-radius:7px}}
    td.resolved{{background:rgba(34,197,94,.10);color:var(--c-resolved);text-align:center;font-weight:700;border-radius:7px}}
    td.only-ms{{background:rgba(96,165,250,.10);color:var(--c-only);text-align:center;font-weight:700;border-radius:7px}}
    /* legend */
    .legend{{display:flex;flex-wrap:wrap;gap:10px;font-size:.8rem;margin-top:12px}}
    .leg{{display:flex;align-items:center;gap:5px}}
    .dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}
    code{{font-family:Consolas,monospace;background:rgba(148,163,184,.1);padding:2px 5px;border-radius:5px}}
    .hidden{{display:none!important}}
    /* symbol-level expand rows */
    tr.row-expandable{{cursor:pointer}}
    tr.row-expandable:hover > td{{background:rgba(56,189,248,.04)}}
    .expand-btn{{display:inline-block;font-size:.7rem;color:var(--muted);width:14px;user-select:none;transition:transform 150ms}}
    tr.sym-row > td{{padding:0;background:rgba(10,15,30,.7);border-bottom:2px solid var(--accent)}}
    .sym-tbl-wrap{{padding:6px 8px 14px 32px}}
    .sym-tbl-wrap table{{font-size:.81rem;width:100%}}
    .sym-tbl-wrap th{{font-size:.7rem;background:rgba(10,15,30,.98)}}
    td.sym-file{{color:var(--muted);font-size:.78rem;max-width:200px;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap;font-family:Consolas,monospace}}
    @media(max-width:1200px){{
      .sunburst-row{{grid-template-columns:1fr 1fr; min-height: auto}}
      .sb-box#symbolSB{{display:none}}
    }}
    @media(max-width:900px){{
      .workspace{{grid-template-columns:1fr}}
      .sunburst-row{{grid-template-columns:1fr}}
      .sidebar{{position:static;max-height:none}}
    }}
  </style>
</head>
<body>
<div class="page">

  <header class="hero">
    <h1>{he(title)}</h1>
    <div class="meta">Generated: {he(generated_at)} &nbsp;&bull;&nbsp; Inputs: {he(input_labels)}</div>
    <div class="cards">
      <div class="card"><div class="card-value">{total_issues}</div><div class="card-label">Total findings</div></div>
      <div class="card"><div class="card-value">{len(projects_meta)}</div><div class="card-label">Projects</div></div>
      <div class="card"><div class="card-value">{len(milestone_order)}</div><div class="card-label">Milestones</div></div>
    </div>
  </header>

  <div class="workspace">

    <aside class="sidebar">
      <h3>Projects &mdash; click to compare</h3>
      <ul class="project-list" id="projectList">{projects_list_html}</ul>
    </aside>

    <div class="main-pane">

      <!-- overview + detail sunbursts side by side -->
      <div class="pane">
        <h2>Issue distribution overview</h2>
        <p class="sub">Overview (left): projects sized by total issues; outer ring = issue types. <br>Detail (center): Milestone &rarr; Issue Type. Click an issue metric (e.g. CMA0005). <br>Third chart (right): methods/classes distribution for the selected metric across milestones.</p>
        <div class="sunburst-row">
          <div class="sb-box">
            <h3>All Projects &rarr; Issue Types</h3>
            <div id="overviewSB"></div>
            <div class="sb-center">
              <strong id="ovLabel">All Projects</strong>
              <span id="ovValue">{total_issues} findings</span>
            </div>
          </div>
          <div class="sb-box">
            <h3 id="detSBTitle">Select a project</h3>
            <div id="detailSB"></div>
            <div class="sb-center">
              <strong id="detLabel">&nbsp;</strong>
              <span id="detValue">&nbsp;</span>
            </div>
          </div>
          <div class="sb-box" id="symbolSB">
            <h3 id="symSBTitle">Click an issue metric</h3>
            <div id="symbolMetricsSB"></div>
            <div class="sb-center">
              <strong id="symLabel">&nbsp;</strong>
              <span id="symValue">&nbsp;</span>
            </div>
          </div>
        </div>
      </div>

      <!-- detail panel -->
      <div class="pane" id="detailPanel">
        <div id="detailPlaceholder">
          <div class="icon">&#9763;</div>
          <p>Click a project in the sidebar or overview sunburst<br>to compare milestones.</p>
        </div>
        <div id="detailContent" class="hidden">
          <h2 id="detTitle"></h2>
          <p class="sub" id="detSub"></p>
          <div class="ms-badges" id="msBadges"></div>
          <h3 style="margin-bottom:8px">Issue persistence across milestones</h3>
          <div class="legend">
            <span class="leg"><span class="dot" style="background:var(--c-new)"></span>New in this milestone</span>
            <span class="leg"><span class="dot" style="background:var(--c-persists)"></span>Persists from previous</span>
            <span class="leg"><span class="dot" style="background:var(--c-resolved)"></span>Resolved (was &gt;0, now 0)</span>
            <span class="leg"><span class="dot" style="background:var(--c-only)"></span>Only one milestone available</span>
          </div>
          <div class="tbl-wrap" id="persTable" style="margin-top:12px"></div>
        </div>
      </div>

    </div>
  </div>
</div>

<script>
/* ── data ── */
const overviewData   = {overview_js};
const perProject     = {per_project_js};
const milestoneOrder = {milestone_order_js};

/* ── colour scales ── */
const cProject   = d3.scaleOrdinal(d3.schemeTableau10);
const cIssue     = d3.scaleOrdinal(d3.schemePastel1);
const cMilestone = d3.scaleOrdinal(d3.schemeSet2);
const cSeverity  = d3.scaleOrdinal()
  .domain(['Error','Warning','Info','Hidden'])
  .range(['#ef4444','#f59e0b','#60a5fa','#94a3b8']);

/* ── sunburst factory ──
  overview depth: root(0) > project(1) > issue-type(2)
  project  depth: root(0) > milestone(1) > issue-type(2)
  metric   depth: root(0) > milestone(1) > symbol(2)
*/
function drawSunburst(containerId, data, size, labelId, valueId, clickCb, mode='auto') {{
  const host = document.getElementById(containerId);
  host.innerHTML = '';
  if (!data || !data.children || !data.children.length) {{
    host.innerHTML = '<p class="muted" style="padding:20px;text-align:center">No data</p>';
    return;
  }}

  const root = d3.hierarchy(data)
    .sum(d => d.value || 0)
    .sort((a,b) => (b.value||0)-(a.value||0));
  d3.partition().size([2*Math.PI, root.height+1])(root);
  root.each(d => d.current = d);

  const r = size/2;

  const isOverview = mode==='overview' || (mode==='auto' && data.children[0] && typeof data.children[0].key !== 'undefined');
  const isProject  = mode==='project';
  const isMetric   = mode==='metric';
  function nodeColor(d) {{
    // find depth-1 ancestor
    let a = d; while(a.depth > 1) a = a.parent;
    const top = a.data.name;
    if (d.depth===1) {{
      if (isOverview) return cProject(top);
      return cMilestone(top);
    }}
    if (d.depth===2) {{
      if (isOverview || isProject) return cIssue(d.data.name);
      if (isMetric) return cProject((d.data.title || d.data.name));
    }}
    return '#6b7280';
  }}

  const arc = d3.arc()
    .startAngle(d => d.x0).endAngle(d => d.x1)
    .padAngle(d => Math.min((d.x1-d.x0)/2, 0.008))
    .padRadius(r*1.5)
    .innerRadius(d => d.y0*r/(root.height+1))
    .outerRadius(d => Math.max(d.y0*r/(root.height+1), d.y1*r/(root.height+1)-1));

  const svg = d3.create('svg')
    .attr('class','sb')
    .attr('width', size)
    .attr('height', size)
    .attr('viewBox',`${{-r}} ${{-r}} ${{size}} ${{size}}`)
    .style('max-width','100%').style('height','auto');

  const paths = svg.append('g').selectAll('path')
    .data(root.descendants().filter(d=>d.depth))
    .join('path')
    .attr('fill', d => nodeColor(d))
    .attr('fill-opacity', d => arcVis(d.current) ? (d.children ? 0.86 : 0.66) : 0)
    .attr('pointer-events', d => arcVis(d.current) ? 'auto' : 'none')
    .attr('d', d => arc(d.current))
    .style('cursor','pointer');

  paths.append('title')
    .text(d => d.ancestors().map(n=>n.data.name).reverse().join(' \u2192 ')+'\\n'+(d.value||0)+' finding(s)');

  paths.on('mouseenter',(_,d)=>{{
    const pathStr = d.ancestors().map(n=>n.data.name).reverse().filter((_,i)=>i>0).join(' \u2192 ') || data.name;
    if(labelId) document.getElementById(labelId).textContent = pathStr;
    if(valueId) document.getElementById(valueId).textContent = (d.value||0)+' finding(s)';
  }});
  paths.on('mouseleave',()=>{{
    if(labelId) document.getElementById(labelId).textContent = data.name;
    if(valueId) document.getElementById(valueId).textContent = (root.value||0)+' finding(s)';
  }});

  if (clickCb) {{
    paths.on('click',(event,d)=>{{
      event.stopPropagation();
      // Project click in overview (depth 1)
      if (isOverview && d.depth===1) {{
        const key = d.data.key || findKey(d.data.name);
        if (key) clickCb({{type: 'project', key}});
      }}
      // Metric click in second diagram (depth 2: root > milestone > issue)
      if (isProject && d.depth===2) {{
        const diag_id = d.data.name;
        if (diag_id) clickCb({{type: 'metric', diag_id}});
      }}
    }});
  }}

  /* centre total */
  svg.append('circle').attr('r',r/(root.height+1)-2)
    .attr('fill','rgba(10,15,30,.92)').attr('stroke','rgba(148,163,184,.15)');
  svg.append('text').attr('text-anchor','middle').attr('dy','-0.25em')
    .attr('fill','#e5e7eb').style('font-size','.7rem').style('font-weight','600').text('Total');
  svg.append('text').attr('text-anchor','middle').attr('dy','1.1em')
    .attr('fill','#38bdf8').style('font-size','1.2rem').style('font-weight','800').text(root.value||0);

  host.appendChild(svg.node());
}}

function arcVis(d) {{
  return d.y1<=4 && d.y0>=1 && d.x1>d.x0;
}}

function findKey(name) {{
  for (const [k,p] of Object.entries(perProject)) if (p.name===name) return k;
  return null;
}}

/* ── sunburst click handler ── */
let activeKey = null;
let activeMetric = null;  // {{diag_id}}

function onSunburstClick(obj) {{
  if (obj.type === 'project') selectProject(obj.key);
  if (obj.type === 'metric') selectMetric(obj);
}}

function selectProject(key) {{
  const pdata = perProject[key];
  if (!pdata) return;
  activeKey = key;
  activeMetric = null;  // reset selected metric when selecting new project
  document.getElementById('symbolMetricsSB').innerHTML = '';
  document.getElementById('symLabel').textContent = '';
  document.getElementById('symValue').textContent = '';
  document.getElementById('symSBTitle').textContent = 'Click an issue metric';

  /* sidebar */
  document.querySelectorAll('.project-item').forEach(el=>
    el.classList.toggle('active', el.dataset.key===key));

  /* detail sunburst */
  document.getElementById('detSBTitle').textContent = pdata.name+' \u2014 Milestone \u2192 Issue';
  drawSunburst('detailSB', pdata.detail_sunburst, 340, 'detLabel', 'detValue', onSunburstClick, 'project');

  /* detail panel */
  document.getElementById('detailPlaceholder').style.display='none';
  document.getElementById('detailContent').classList.remove('hidden');
  document.getElementById('detTitle').textContent = pdata.name;
  document.getElementById('detSub').textContent =
    pdata.total+' finding(s) across '+Object.keys(pdata.milestones).length+' milestone(s)';

  /* milestone badges */
  const badgesEl = document.getElementById('msBadges');
  badgesEl.innerHTML = '';
  for (const lbl of milestoneOrder) {{
    const ms = pdata.milestones[lbl];
    const el = document.createElement('div');
    el.className='ms-badge';
    const subHtml = ms && ms.sub_project_names && ms.sub_project_names.length
      ? `<div class="ms-subs">${{ms.sub_project_names.map(s=>`<span class="sub-tag">${{esc(s)}}</span>`).join('')}}</div>` : '';
    el.innerHTML = `<div class="ms-name">${{lbl}}</div>`
      +(ms ? `<div class="ms-count">${{ms.total}}</div><div class="ms-ref">${{ms.ref_label}}</div>${{subHtml}}` : '');
    badgesEl.appendChild(el);
  }}
  buildPersistenceTable(pdata);
  document.getElementById('detailPanel').scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}

function selectMetric(obj) {{
  const {{diag_id}} = obj;
  activeMetric = obj;
  const pdata = perProject[activeKey];
  if (!pdata) return;

  const metric_rows = (pdata.symbol_comparison || {{}})[diag_id] || [];
  if (!metric_rows.length) {{
    document.getElementById('symbolMetricsSB').innerHTML = '<p class="muted" style="padding:20px;text-align:center">No method/class data for this metric.</p>';
    document.getElementById('symSBTitle').textContent = `${{esc(diag_id)}} \u2014 details`;
    return;
  }}

  document.getElementById('symSBTitle').textContent = `${{esc(diag_id)}} \u2014 Methods/Classes`;

  // Build third sunburst: Metric -> Milestone -> Methods/Classes
  const present = milestoneOrder.filter(lbl => pdata.milestones[lbl]);
  const metrics_root = {{
    name: diag_id,
    children: present.map(lbl => {{
      const symbols = metric_rows
        .filter(r => r.by_milestone && r.by_milestone[lbl])
        .map(r => ({{
          name: r.symbol,
          title: r.sub_project,
          value: 1,
        }}));
      return {{ name: lbl, children: symbols }};
    }}).filter(m => m.children.length>0),
  }};

  drawSunburst('symbolMetricsSB', metrics_root, 320, 'symLabel', 'symValue', null, 'metric');
}}

function buildPersistenceTable(pdata) {{
  const present = milestoneOrder.filter(lbl => pdata.milestones[lbl]);
  const wrap = document.getElementById('persTable');
  const only = present.length===1;
  const colSpan = present.length + 3;  // expand-btn + id + title + milestone cols

  let h = '<table><thead><tr><th style="width:22px"></th><th>Issue ID</th><th>Title</th>';
  for (const lbl of present) h += `<th>${{esc(lbl)}}</th>`;
  h += '</tr></thead><tbody>';

  for (const row of pdata.persistence_rows) {{
    const counts = present.map(lbl => row.by_milestone[lbl]||0);
    if (counts.every(c=>c===0)) continue;
    const hasSym = !!(pdata.symbol_comparison && pdata.symbol_comparison[row.diag_id] && pdata.symbol_comparison[row.diag_id].length);
    const btn = hasSym ? '<span class="expand-btn" title="Expand methods / classes">&#9654;</span>' : '';

    h += `<tr class="${{hasSym ? 'row-expandable' : ''}}" data-diag="${{esc(row.diag_id)}}">` ;
    h += `<td style="padding:6px 4px">${{btn}}</td>`;
    h += `<td><code>${{esc(row.diag_id)}}</code></td><td>${{esc(row.title)}}</td>`;
    for (let i=0; i<present.length; i++) {{
      const c = counts[i];
      const prev = i>0 ? counts[i-1] : null;
      if (only) {{
        h += c>0 ? `<td class="only-ms">${{c}}</td>` : '<td class="absent">\u2014</td>';
        continue;
      }}
      if (c===0) {{
        const anyBefore = counts.slice(0,i).some(x=>x>0);
        h += anyBefore ? '<td class="resolved">0</td>' : '<td class="absent">\u2014</td>';
        continue;
      }}
      let cls;
      if (prev===null || prev===0) cls = 'new-issue';
      else cls = 'persists';
      h += `<td class="${{cls}}">${{c}}</td>`;
    }}
    h += '</tr>';
    if (hasSym) {{
      h += `<tr class="sym-row hidden" data-diag="${{esc(row.diag_id)}}"><td colspan="${{colSpan}}" class="sym-row-td"></td></tr>`;
    }}
  }}

  h += '</tbody></table>';
  wrap.innerHTML = h;

  /* attach expand/collapse handlers */
  wrap.querySelectorAll('tr.row-expandable').forEach(tr => {{
    tr.addEventListener('click', () => {{
      const diagId = tr.dataset.diag;
      const symRow = wrap.querySelector(`tr.sym-row[data-diag="${{diagId}}"]`);
      if (!symRow) return;
      const isHidden = symRow.classList.toggle('hidden');
      const btn = tr.querySelector('.expand-btn');
      if (btn) btn.innerHTML = isHidden ? '&#9654;' : '&#9660;';
      if (!isHidden && !symRow.dataset.built) {{
        symRow.dataset.built = '1';
        symRow.querySelector('.sym-row-td').innerHTML =
          buildSymbolTable(perProject[activeKey], diagId);
      }}
    }});
  }});
}}

function buildSymbolTable(pdata, diagId) {{
  const present = milestoneOrder.filter(lbl => pdata.milestones[lbl]);
  const rows = (pdata.symbol_comparison || {{}})[diagId] || [];
  if (!rows.length) return '<p style="padding:10px 32px;color:var(--muted)">No symbol data available.</p>';

  let h = '<div class="sym-tbl-wrap"><table><thead><tr>';
  h += '<th>Sub-project</th><th>Symbol / Method / Class</th><th>File</th>';
  for (const lbl of present) h += `<th>${{esc(lbl)}}</th>`;
  h += '</tr></thead><tbody>';

  for (const row of rows) {{
    const vals = present.map(lbl => row.by_milestone[lbl] || null);
    if (vals.every(v=>!v)) continue;

    h += '<tr>';
    h += `<td>${{esc(row.sub_project)}}</td>`;
    h += `<td><code>${{esc(row.symbol)}}</code></td>`;
    h += `<td class="sym-file" title="${{esc(row.file)}}">${{esc(symShortPath(row.file))}}</td>`;
    for (let i=0; i<present.length; i++) {{
      const v = vals[i];
      const prev = i>0 ? vals[i-1] : undefined;
      if (!v) {{
        const anyBefore = vals.slice(0,i).some(x=>!!x);
        h += anyBefore ? '<td class="resolved" title="Resolved">&#10003;</td>' : '<td class="absent">\u2014</td>';
        continue;
      }}
      let cls;
      if (present.length===1) cls='only-ms';
      else if (prev===undefined || !prev) cls='new-issue';
      else cls='persists';
      const display = v.value != null ? v.value : '\u2713';
      const lineInfo = v.line ? ` line ${{v.line}}` : '';
      h += `<td class="${{cls}}" title="${{esc(row.file)}}${{lineInfo}}">${{esc(String(display))}}</td>`;
    }}
    h += '</tr>';
  }}

  h += '</tbody></table></div>';
  return h;
}}

function symShortPath(f) {{
  if (!f) return '\u2014';
  const parts = f.split('/');
  return parts.length > 2 ? '\u2026/' + parts.slice(-2).join('/') : f;
}}

function esc(s){{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

/* ── initial overview render ── */
drawSunburst('overviewSB', overviewData, 360, 'ovLabel', 'ovValue', onSunburstClick, 'overview');

/* ── sidebar click ── */
document.querySelectorAll('.project-item').forEach(el=>
  el.addEventListener('click',()=>selectProject(el.dataset.key)));
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    input_files = resolve_input_files(list(args.inputs))
    if not input_files:
        raise SystemExit("No matching input files found.")

    entries: list[dict] = []
    for path in input_files:
        entries.extend(load_entries_from_file(path))
    if not entries:
        raise SystemExit("No supported analyzer records found in the selected files.")

    html = render_report(entries, input_files, args.title)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = WORKSPACE / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"HTML report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
