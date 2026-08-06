from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

try:
    import plotly.express as px
except Exception:
    px = None

METHOD_METRICS = {
    "bumpy_road_score",
    "parameter_count",
    "maintainability_index",
    "cyclomatic_complexity",
}

CLASS_METRICS = {
    "lcom4_score",
    "lcom5_score",
    "class_coupling",
}

METHOD_MESSAGE_RE = re.compile(r"Method '([^']+)'.*?\(([-+]?[0-9]*\.?[0-9]+)\)")
CLASS_MESSAGE_RE = re.compile(r"Class '([^']+)'.*?\(([-+]?[0-9]*\.?[0-9]+)\)")
CLASS_COUPLING_MESSAGE_RE = re.compile(r"'([^']+)' has a high class coupling value \(([-+]?[0-9]*\.?[0-9]+)\)")
MILESTONE_RE = re.compile(r"method_analysis_results_(\d+)")


def _source_label(path: Path) -> str:
    m = MILESTONE_RE.search(path.stem)
    if m:
        return f"Milestone {m.group(1)}"
    return path.stem


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _extract_from_message(message: str) -> tuple[str | None, float | None]:
    m = METHOD_MESSAGE_RE.search(message or "")
    if not m:
        return None, None
    method_name = m.group(1)
    try:
        metric_value = float(m.group(2))
    except ValueError:
        metric_value = None
    return method_name, metric_value


def _extract_class_from_message(message: str) -> tuple[str | None, float | None]:
    m = CLASS_MESSAGE_RE.search(message or "") or CLASS_COUPLING_MESSAGE_RE.search(message or "")
    if not m:
        return None, None
    class_name = m.group(1)
    try:
        metric_value = float(m.group(2))
    except ValueError:
        metric_value = None
    return class_name, metric_value


def _is_method_level(metric_name: str | None, message: str) -> bool:
    if metric_name in METHOD_METRICS:
        return True
    return "Method '" in (message or "")


def _is_class_level(metric_name: str | None, message: str) -> bool:
    if metric_name in CLASS_METRICS:
        return True
    msg = message or ""
    return "Class '" in msg or "class coupling" in msg


def _entity_kind(metric_name: str | None, message: str) -> str | None:
    if _is_method_level(metric_name, message):
        return "Method"
    if _is_class_level(metric_name, message):
        return "Class"
    return None


def _extract_entity_symbol(metric_name: str | None, symbol: object, message: str) -> str:
    raw = str(symbol).strip() if symbol is not None else ""
    if raw:
        return raw

    if _is_method_level(metric_name, message):
        method_symbol, _ = _extract_from_message(message)
        return method_symbol or "(unknown)"

    if _is_class_level(metric_name, message):
        class_symbol, _ = _extract_class_from_message(message)
        return class_symbol or "(unknown)"

    return "(unknown)"


def _file_identity(file_path: str) -> str:
    """Return a stable, shorter file identity for grouping across versions."""
    if not file_path:
        return "unknown"
    p = Path(file_path)
    parts = [part for part in p.parts if part not in ("/", "\\")]
    if len(parts) >= 3:
        return "/".join(parts[-3:])
    if parts:
        return "/".join(parts)
    return "unknown"


def load_student_method_records(paths: Iterable[Path]) -> pd.DataFrame:
    rows: list[dict] = []

    for path in paths:
        source_label = _source_label(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for key, record in data.items():
            diagnostics = record.get("diagnostics", []) if isinstance(record, dict) else []
            parts = str(key).split("_", 1)
            project_id = parts[0]
            commit_ref = parts[1] if len(parts) > 1 else str(key)

            for d in diagnostics:
                message = str(d.get("message", ""))
                metric_name = d.get("metric_name")
                if not _is_method_level(metric_name, message):
                    continue

                symbol = d.get("symbol")
                metric_value = _as_float(d.get("metric_value"))
                msg_symbol, msg_value = _extract_from_message(message)
                method_name = symbol or msg_symbol or "(unknown)"
                file_path = str(d.get("file_path") or "")
                location = _file_identity(file_path)

                rows.append(
                    {
                        "dataset": "student",
                        "source": source_label,
                        "project": f"Project {project_id}",
                        "ref": commit_ref,
                        "method": method_name,
                        "method_instance": f"{method_name} @ {location}",
                        "metric_name": metric_name or "unknown",
                        "metric_value": metric_value if metric_value is not None else msg_value,
                        "severity": d.get("severity", "Unknown"),
                        "diagnostic_id": d.get("diagnostic_id", "Unknown"),
                    }
                )

    return pd.DataFrame(rows)


def load_student_project_totals(paths: Iterable[Path]) -> pd.DataFrame:
    """Load per-project totals (methods/classes) for each student milestone file."""
    rows: list[dict] = []

    for path in paths:
        source_label = _source_label(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for key, record in data.items():
            if not isinstance(record, dict):
                continue

            parts = str(key).split("_", 1)
            project_id = parts[0]
            commit_ref = parts[1] if len(parts) > 1 else str(key)

            summary_all = record.get("summary", {}).get("all", {})
            summary_filtered = record.get("summary", {}).get("filtered", {})
            method_count = int(_as_float(summary_all.get("method_count")) or 0)
            class_count = int(_as_float(summary_all.get("class_count")) or 0)
            filtered_method_count = int(_as_float(summary_filtered.get("method_count")) or 0)
            filtered_class_count = int(_as_float(summary_filtered.get("class_count")) or 0)

            rows.append(
                {
                    "source": source_label,
                    "project": f"Project {project_id}",
                    "ref": commit_ref,
                    "total_methods": method_count,
                    "total_classes": class_count,
                    "total_entities": method_count + class_count,
                    "filtered_methods": filtered_method_count,
                    "filtered_classes": filtered_class_count,
                    "filtered_entities": filtered_method_count + filtered_class_count,
                }
            )

    return pd.DataFrame(rows)


def load_student_problem_entity_records(paths: Iterable[Path]) -> pd.DataFrame:
    """Load problematic methods/classes from diagnostics for per-milestone drill-down views."""
    rows: list[dict] = []

    for path in paths:
        source_label = _source_label(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for key, record in data.items():
            if not isinstance(record, dict):
                continue

            diagnostics = record.get("diagnostics", [])
            parts = str(key).split("_", 1)
            project_id = parts[0]
            commit_ref = parts[1] if len(parts) > 1 else str(key)

            for d in diagnostics:
                message = str(d.get("message", ""))
                metric_name = d.get("metric_name")
                entity_type = _entity_kind(metric_name, message)
                if entity_type is None:
                    continue

                rows.append(
                    {
                        "source": source_label,
                        "project": f"Project {project_id}",
                        "ref": commit_ref,
                        "entity_type": entity_type,
                        "entity": _extract_entity_symbol(metric_name, d.get("symbol"), message),
                        "metric_name": metric_name or "unknown",
                        "severity": d.get("severity", "Unknown"),
                        "diagnostic_id": d.get("diagnostic_id", "Unknown"),
                    }
                )

    return pd.DataFrame(rows)


def load_public_method_records(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for project_key, versions in data.items():
        if not isinstance(versions, dict):
            continue

        for idx, entry in versions.items():
            if not isinstance(entry, dict):
                continue
            diagnostics = entry.get("diagnostics", [])
            tag = entry.get("tag") or str(idx)

            for d in diagnostics:
                message = str(d.get("message", ""))
                metric_name = d.get("metric_name")
                if not _is_method_level(metric_name, message):
                    continue

                symbol = d.get("symbol")
                metric_value = _as_float(d.get("metric_value"))
                msg_symbol, msg_value = _extract_from_message(message)
                method_name = symbol or msg_symbol or "(unknown)"
                file_path = str(d.get("file_path") or "")
                location = _file_identity(file_path)

                rows.append(
                    {
                        "dataset": "public",
                        "source": "Public projects",
                        "project": str(project_key),
                        "ref": str(tag),
                        "method": method_name,
                        "method_instance": f"{method_name} @ {location}",
                        "metric_name": metric_name or "unknown",
                        "metric_value": metric_value if metric_value is not None else msg_value,
                        "severity": d.get("severity", "Unknown"),
                        "diagnostic_id": d.get("diagnostic_id", "Unknown"),
                    }
                )

    return pd.DataFrame(rows)


def load_public_project_totals(path: Path) -> pd.DataFrame:
    """Load per-project totals (methods/classes) for each public project version/tag."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for project_key, versions in data.items():
        if not isinstance(versions, dict):
            continue

        for idx, entry in versions.items():
            if not isinstance(entry, dict):
                continue

            tag = entry.get("tag") or str(idx)
            summary_all = entry.get("summary", {}).get("all", {})
            summary_filtered = entry.get("summary", {}).get("filtered", {})

            method_count = int(_as_float(summary_all.get("method_count")) or 0)
            class_count = int(_as_float(summary_all.get("class_count")) or 0)
            filtered_method_count = int(_as_float(summary_filtered.get("method_count")) or 0)
            filtered_class_count = int(_as_float(summary_filtered.get("class_count")) or 0)

            rows.append(
                {
                    "source": "Public projects",
                    "project": str(project_key),
                    "ref": str(tag),
                    "total_methods": method_count,
                    "total_classes": class_count,
                    "total_entities": method_count + class_count,
                    "filtered_methods": filtered_method_count,
                    "filtered_classes": filtered_class_count,
                    "filtered_entities": filtered_method_count + filtered_class_count,
                }
            )

    return pd.DataFrame(rows)


def load_public_problem_entity_records(path: Path) -> pd.DataFrame:
    """Load problematic methods/classes for each public project version/tag."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for project_key, versions in data.items():
        if not isinstance(versions, dict):
            continue

        for idx, entry in versions.items():
            if not isinstance(entry, dict):
                continue

            tag = entry.get("tag") or str(idx)
            diagnostics = entry.get("diagnostics", [])

            for d in diagnostics:
                message = str(d.get("message", ""))
                metric_name = d.get("metric_name")
                entity_type = _entity_kind(metric_name, message)
                if entity_type is None:
                    continue

                rows.append(
                    {
                        "source": "Public projects",
                        "project": str(project_key),
                        "ref": str(tag),
                        "entity_type": entity_type,
                        "entity": _extract_entity_symbol(metric_name, d.get("symbol"), message),
                        "metric_name": metric_name or "unknown",
                        "severity": d.get("severity", "Unknown"),
                        "diagnostic_id": d.get("diagnostic_id", "Unknown"),
                    }
                )

    return pd.DataFrame(rows)


def _save_fig(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip())
    slug = slug.strip("_").lower()
    return slug or "project"


def _comparison_dim(project_df: pd.DataFrame) -> str:
    # Prefer milestone/source comparison for student data.
    if project_df["source"].nunique(dropna=True) > 1:
        return "source"
    # Fallback to ref (e.g., tags in public projects).
    if project_df["ref"].nunique(dropna=True) > 1:
        return "ref"
    return "source"


def generate_per_project_comparisons(df: pd.DataFrame, out_dir: Path, title_prefix: str) -> None:
    if df.empty:
        return

    per_project_dir = out_dir / "per_project"
    per_project_dir.mkdir(parents=True, exist_ok=True)

    for project_name, project_df in df.groupby("project"):
        compare_dim = _comparison_dim(project_df)
        project_slug = _slugify(str(project_name))

        # 1) Per-project top method instances compared across milestones/tags.
        method_col = "method_instance" if "method_instance" in project_df.columns else "method"
        top_methods = (
            project_df.groupby(method_col, as_index=False)
            .size()
            .sort_values("size", ascending=False)
            .head(12)[method_col]
            .tolist()
        )
        top_methods_df = project_df[project_df[method_col].isin(top_methods)]
        if not top_methods_df.empty:
            preferred_cols = _milestone_order(list(pd.unique(top_methods_df[compare_dim].dropna())))
            method_pivot = (
                top_methods_df.groupby([method_col, compare_dim], as_index=False)
                .size()
                .pivot(index=method_col, columns=compare_dim, values="size")
                .fillna(0)
            )
            ordered_cols = [c for c in preferred_cols if c in method_pivot.columns] + [
                c for c in method_pivot.columns if c not in preferred_cols
            ]
            method_pivot = method_pivot.reindex(columns=ordered_cols)

            plt.figure(figsize=(10, max(5, 0.4 * len(method_pivot.index))))
            sns.heatmap(method_pivot, annot=True, fmt=".0f", cmap="Blues", cbar_kws={"label": "Findings"})
            plt.title(f"{title_prefix} - {project_name}: Top Method Instances by {compare_dim.title()}")
            plt.xlabel(compare_dim.title())
            plt.ylabel("Method instance")
            _save_fig(per_project_dir / f"{project_slug}_top_methods_by_{compare_dim}.png")

        # 2) Per-project metric distribution compared across milestones/tags.
        numeric_df = project_df.dropna(subset=["metric_value"]).copy()
        if not numeric_df.empty and numeric_df[compare_dim].nunique(dropna=True) > 1:
            hue_order = _milestone_order(list(pd.unique(numeric_df[compare_dim].dropna())))
            plt.figure(figsize=(12, 6))
            sns.boxplot(data=numeric_df, x="metric_name", y="metric_value", hue=compare_dim, hue_order=hue_order)
            plt.title(f"{title_prefix} - {project_name}: Metric Value Distribution by {compare_dim.title()}")
            plt.xlabel("Metric")
            plt.ylabel("Metric value")
            plt.xticks(rotation=20, ha="right")
            plt.legend(title=compare_dim.title(), bbox_to_anchor=(1.02, 1), loc="upper left")
            _save_fig(per_project_dir / f"{project_slug}_metric_distribution_by_{compare_dim}.png")
        else:
            # Fallback if numeric values are unavailable: compare finding counts.
            count_df = (
                project_df.groupby(["metric_name", compare_dim], as_index=False)
                .size()
                .rename(columns={"size": "findings"})
            )
            if not count_df.empty:
                hue_order = _milestone_order(list(pd.unique(count_df[compare_dim].dropna())))
                plt.figure(figsize=(12, 6))
                sns.barplot(data=count_df, x="metric_name", y="findings", hue=compare_dim, hue_order=hue_order)
                plt.title(f"{title_prefix} - {project_name}: Metric Findings by {compare_dim.title()}")
                plt.xlabel("Metric")
                plt.ylabel("Findings")
                plt.xticks(rotation=20, ha="right")
                plt.legend(title=compare_dim.title(), bbox_to_anchor=(1.02, 1), loc="upper left")
                _save_fig(per_project_dir / f"{project_slug}_metric_findings_by_{compare_dim}.png")


def generate_sunburst_charts(
    df: pd.DataFrame,
    out_dir: Path,
    title_prefix: str,
    totals_df: pd.DataFrame | None = None,
    entity_df: pd.DataFrame | None = None,
) -> None:
    if df.empty or px is None:
        if px is None:
            print("Plotly is not installed. Skipping sunburst charts.")
        return

    sunburst_dir = out_dir / "sunburst"
    sunburst_dir.mkdir(parents=True, exist_ok=True)

    # Interactive drill-down:
    # project -> milestone/tag(with percentage) -> class/method -> symbol
    if totals_df is not None and entity_df is not None and not totals_df.empty and not entity_df.empty:
        compare_dim = _comparison_dim(totals_df)
        summary = (
            totals_df.groupby(["project", compare_dim], as_index=False)[
                ["total_methods", "total_classes", "total_entities", "filtered_methods", "filtered_classes", "filtered_entities"]
            ]
            .max()
        )
        summary["problem_pct"] = summary.apply(
            lambda r: (100.0 * r["filtered_entities"] / r["total_entities"]) if r["total_entities"] > 0 else 0.0,
            axis=1,
        )
        summary["version_label"] = summary.apply(
            lambda r: f"{r[compare_dim]} ({r['problem_pct']:.1f}%)",
            axis=1,
        )

        entity_agg = (
            entity_df.groupby(["project", compare_dim, "entity_type", "entity", "metric_name"], as_index=False)
            .size()
            .rename(columns={"size": "findings"})
        )

        if not entity_agg.empty:
            entity_enriched = entity_agg.merge(
                summary[["project", compare_dim, "version_label", "problem_pct"]],
                on=["project", compare_dim],
                how="left",
            )
            entity_enriched["version_label"] = entity_enriched["version_label"].fillna(entity_enriched[compare_dim])

            # Check data size to decide whether to create per-project or global sunburst
            total_entities = len(entity_enriched)
            project_count = entity_enriched["project"].nunique()

            # For public projects or very large datasets, create per-project sunbursts
            if project_count > 5 or total_entities > 5000:
                per_project_sunburst_dir = sunburst_dir / "per_project"
                per_project_sunburst_dir.mkdir(parents=True, exist_ok=True)

                for project, project_data in entity_enriched.groupby("project"):
                    project_slug = _slugify(str(project))

                    fig = px.sunburst(
                        project_data,
                        path=["version_label", "entity_type", "entity"],
                        values="findings",
                        title=f"{title_prefix} - {project}: Problematic Methods/Classes",
                        color="entity_type",
                        hover_data={"problem_pct": ":.2f", "metric_name": True, "findings": True},
                    )
                    fig.write_html(
                        str(per_project_sunburst_dir / f"{project_slug}_entities_sunburst.html"),
                        include_plotlyjs="cdn",
                    )

                # Create summary sunburst: project → version → metric (no methods)
                metric_summary = (
                    entity_enriched.groupby(["project", "version_label", "metric_name"], as_index=False)
                    .agg(findings=("findings", "sum"))
                )

                fig_summary = px.sunburst(
                    metric_summary,
                    path=["project", "version_label", "metric_name"],
                    values="findings",
                    title=f"{title_prefix} - Summary: Findings by Version and Metric",
                    color="metric_name",
                )
                fig_summary.write_html(
                    str(sunburst_dir / "summary_project_version_metric_sunburst.html"),
                    include_plotlyjs="cdn",
                )
                fig_summary.write_html(
                    str(sunburst_dir / "project_ref_metric_sunburst.html"),
                    include_plotlyjs="cdn",
                )

            else:
                # For smaller datasets, use the full drill-down
                fig1 = px.sunburst(
                    entity_enriched,
                    path=["project", "version_label", "entity_type", "entity"],
                    values="findings",
                    title=(
                        f"{title_prefix} - Problem Summary by Version (%) "
                        "→ Problematic Methods/Classes"
                    ),
                    color="entity_type",
                    hover_data={"problem_pct": ":.2f", "metric_name": True, "findings": True},
                )
                fig1.write_html(
                    str(sunburst_dir / "project_milestone_problematic_entities_sunburst.html"),
                    include_plotlyjs="cdn",
                )
                fig1.write_html(
                    str(sunburst_dir / "project_metric_method_sunburst.html"),
                    include_plotlyjs="cdn",
                )

                fig2 = px.sunburst(
                    entity_enriched,
                    path=["project", "version_label", "entity_type", "metric_name", "entity"],
                    values="findings",
                    title=f"{title_prefix} - Version Drill-down (Metric → Method/Class)",
                    color="metric_name",
                )
                fig2.write_html(
                    str(sunburst_dir / "project_milestone_metric_entity_sunburst.html"),
                    include_plotlyjs="cdn",
                )
                fig2.write_html(
                    str(sunburst_dir / "project_ref_metric_sunburst.html"),
                    include_plotlyjs="cdn",
                )

        return

    # Fallback/legacy sunbursts for non-student datasets.
    agg1 = (
        df.groupby(["project", "metric_name", "method"], as_index=False)
        .size()
        .rename(columns={"size": "findings"})
    )
    if not agg1.empty:
        fig1 = px.sunburst(
            agg1,
            path=["project", "metric_name", "method"],
            values="findings",
            title=f"{title_prefix} - Sunburst (Project → Metric → Method)",
            color="metric_name",
        )
        fig1.write_html(str(sunburst_dir / "project_metric_method_sunburst.html"), include_plotlyjs="cdn")

    agg2 = (
        df.groupby(["project", "ref", "metric_name"], as_index=False)
        .size()
        .rename(columns={"size": "findings"})
    )
    if not agg2.empty:
        fig2 = px.sunburst(
            agg2,
            path=["project", "ref", "metric_name"],
            values="findings",
            title=f"{title_prefix} - Sunburst (Project → Ref → Metric)",
            color="metric_name",
        )
        fig2.write_html(str(sunburst_dir / "project_ref_metric_sunburst.html"), include_plotlyjs="cdn")


def generate_problematic_toplist(entity_df: pd.DataFrame, out_dir: Path, title_prefix: str) -> None:
    """Create a toplist of most problematic methods/classes across milestones."""
    if entity_df.empty:
        return

    metric_pool_size = {"Method": len(METHOD_METRICS), "Class": len(CLASS_METRICS)}

    compare_dim = _comparison_dim(entity_df)

    toplist = (
        entity_df.groupby(["project", "entity_type", "entity"], as_index=False)
        .agg(
            findings=("metric_name", "size"),
            bad_metric_count=("metric_name", "nunique"),
            milestone_coverage=(compare_dim, "nunique"),
        )
    )
    toplist["max_metric_count"] = toplist["entity_type"].map(metric_pool_size).fillna(1)
    toplist["metric_coverage_pct"] = 100.0 * toplist["bad_metric_count"] / toplist["max_metric_count"]
    toplist["problem_score"] = (
        toplist["findings"] * (1.0 + toplist["metric_coverage_pct"] / 100.0)
        + toplist["milestone_coverage"]
    )

    toplist = toplist.sort_values("problem_score", ascending=False)
    toplist_top = toplist.head(30).copy()
    toplist_top["entity_project"] = (
        toplist_top["project"] + " :: " + toplist_top["entity_type"] + " :: " + toplist_top["entity"]
    )

    toplist.sort_values("problem_score", ascending=False).to_csv(
        out_dir / "07_problematic_code_toplist.csv",
        index=False,
        encoding="utf-8",
    )

    if not toplist_top.empty:
        plt.figure(figsize=(14, max(7, 0.36 * len(toplist_top))))
        sns.barplot(
            data=toplist_top,
            y="entity_project",
            x="problem_score",
            hue="entity_type",
            dodge=False,
            palette="Set2",
        )
        plt.title(f"{title_prefix} - Top Problematic Methods/Classes (Composite Score)")
        plt.xlabel("Problem score")
        plt.ylabel("Code element")
        _save_fig(out_dir / "08_problematic_code_toplist.png")


def _milestone_order(values: Iterable[str]) -> list[str]:
    def sort_key(v: str) -> tuple:
        s = str(v)
        # Natural sort key for tags/refs (e.g., v10.8.8 < v10.10.10).
        chunks = re.findall(r"\d+|\D+", s.lower())
        key: list[tuple[int, int | str]] = []
        for ch in chunks:
            if ch.isdigit():
                key.append((0, int(ch)))
            else:
                key.append((1, ch))
        return tuple(key)

    unique = pd.unique(pd.Series(list(values)).dropna())
    return sorted([str(v) for v in unique], key=sort_key)


def generate_metric_by_version_table(
    df: pd.DataFrame,
    out_dir: Path,
    title_prefix: str,
) -> None:
    """
    Generate a heatmap showing findings by metric and version/milestone.
    Similar to top methods comparison but organized by metric.
    """
    if df.empty:
        return

    compare_dim = _comparison_dim(df)

    # Aggregate findings by metric and version/milestone
    metric_version = (
        df.groupby(["metric_name", compare_dim], as_index=False)
        .size()
        .rename(columns={"size": "findings"})
    )

    if metric_version.empty:
        return

    # Create pivot table: metrics as rows, versions as columns
    pivot_table = metric_version.pivot(
        index="metric_name",
        columns=compare_dim,
        values="findings"
    ).fillna(0)

    # Order columns by version
    order = _milestone_order(pivot_table.columns.tolist())
    if order:
        ordered_cols = [c for c in order if c in pivot_table.columns]
        pivot_table = pivot_table[ordered_cols]

    # Generate heatmap
    plt.figure(figsize=(max(8, 1.5 * len(pivot_table.columns)), 6))
    sns.heatmap(
        pivot_table,
        annot=True,
        fmt=".0f",
        cmap="YlOrRd",
        cbar_kws={"label": "Findings"},
    )
    plt.title(f"{title_prefix} - Findings by Metric and Version")
    plt.xlabel(compare_dim.title())
    plt.ylabel("Metric")
    plt.xticks(rotation=20, ha="right")
    _save_fig(out_dir / "09_findings_by_metric_and_version.png")

    # Also save as CSV for detailed reference
    pivot_table.to_csv(out_dir / "09_findings_by_metric_and_version.csv")


def generate_top_fluctuating_methods_table(
    df: pd.DataFrame,
    out_dir: Path,
    title_prefix: str,
    top_n: int = 25,
) -> None:
    """
    Generate a top-method table for the largest fluctuations between milestones/versions.
    Fluctuation score ignores zero values (inactive milestones do not affect score).
    """
    if df.empty:
        return

    method_col = "method_instance" if "method_instance" in df.columns else "method"
    per_project_dir = out_dir / "per_project"
    per_project_dir.mkdir(parents=True, exist_ok=True)

    def _fluctuation(row: pd.Series) -> float:
        non_zero = row[row > 0]
        if len(non_zero) < 2:
            return 0.0
        # Sum of absolute changes across consecutive non-zero milestones.
        return float(non_zero.diff().abs().dropna().sum())

    for project_name, project_df in df.groupby("project"):
        compare_dim = _comparison_dim(project_df)
        project_slug = _slugify(str(project_name))

        method_counts = (
            project_df.groupby([method_col, compare_dim], as_index=False)
            .size()
            .rename(columns={"size": "findings"})
        )
        if method_counts.empty:
            continue

        pivot = method_counts.pivot(index=method_col, columns=compare_dim, values="findings").fillna(0)
        order = _milestone_order(pivot.columns.tolist())
        if order:
            ordered_cols = [c for c in order if c in pivot.columns] + [c for c in pivot.columns if c not in order]
            pivot = pivot.reindex(columns=ordered_cols)

        scores = pivot.apply(_fluctuation, axis=1).rename("fluctuation_score")
        active_counts = pivot.apply(lambda r: int((r > 0).sum()), axis=1).rename("active_versions")
        max_value = pivot.max(axis=1).rename("max_findings")
        min_non_zero = pivot.replace(0, pd.NA).min(axis=1).fillna(0).rename("min_non_zero_findings")

        ranking = pd.concat([scores, active_counts, max_value, min_non_zero], axis=1)
        ranking = ranking.sort_values(["fluctuation_score", "active_versions", "max_findings"], ascending=False)
        ranking = ranking[ranking["fluctuation_score"] > 0]
        if ranking.empty:
            continue

        top_methods = ranking.head(top_n)
        top_pivot = pivot.loc[top_methods.index]

        ranking_out = top_methods.reset_index().rename(columns={method_col: "method"})
        ranking_out.to_csv(
            per_project_dir / f"{project_slug}_top_fluctuating_methods.csv",
            index=False,
            encoding="utf-8",
        )

        plt.figure(figsize=(11, max(6, 0.38 * len(top_pivot.index))))
        sns.heatmap(top_pivot, annot=True, fmt=".0f", cmap="rocket_r", cbar_kws={"label": "Findings"})
        plt.title(
            f"{title_prefix} - {project_name}: Top Fluctuating Methods by {compare_dim.title()} "
            "(zeros ignored in score)"
        )
        plt.xlabel(compare_dim.title())
        plt.ylabel("Method")
        _save_fig(per_project_dir / f"{project_slug}_top_fluctuating_methods_heatmap.png")


def generate_method_percentage_comparison(
    df: pd.DataFrame,
    totals_df: pd.DataFrame,
    out_dir: Path,
    title_prefix: str,
) -> None:
    """
    Compare method findings across milestones as percentages using
    total_methods + total_classes as denominator.
    """
    if totals_df.empty:
        return

    compare_dim = _comparison_dim(totals_df)

    totals = totals_df.groupby(["project", compare_dim], as_index=False).agg(
        total_entities=("total_entities", "max"),
        filtered_entities=("filtered_entities", "max"),
    )
    if totals.empty:
        return

    # Public projects: merge releases by per-project order (Release 1, Release 2, ...).
    chart_dim = compare_dim
    if compare_dim == "ref":
        ordered = []
        for project_name, g in totals.groupby("project"):
            refs = [str(v) for v in pd.unique(g["ref"].dropna())]
            for i, ref in enumerate(_milestone_order(refs), start=1):
                ordered.append({"project": project_name, "ref": ref, "release_step": f"Release {i}"})
        if ordered:
            step_df = pd.DataFrame(ordered)
            totals = totals.merge(step_df, on=["project", "ref"], how="left")
            totals["release_step"] = totals["release_step"].fillna("Release ?")
            chart_dim = "release_step"

    comparison = totals.copy()
    comparison["method_findings_pct"] = comparison.apply(
        lambda r: (100.0 * r["filtered_entities"] / r["total_entities"]) if r["total_entities"] > 0 else 0.0,
        axis=1,
    )

    milestone_summary = (
        comparison.groupby(chart_dim, as_index=False)
        .agg(filtered_entities=("filtered_entities", "sum"), total_entities=("total_entities", "sum"))
    )
    milestone_summary["method_findings_pct"] = milestone_summary.apply(
        lambda r: (100.0 * r["filtered_entities"] / r["total_entities"]) if r["total_entities"] > 0 else 0.0,
        axis=1,
    )

    order = _milestone_order(milestone_summary[chart_dim].tolist())
    if order:
        milestone_summary[chart_dim] = pd.Categorical(milestone_summary[chart_dim], categories=order, ordered=True)
        milestone_summary = milestone_summary.sort_values(chart_dim)

    plt.figure(figsize=(10, 5))
    sns.barplot(
        data=milestone_summary,
        x=chart_dim,
        y="method_findings_pct",
        hue=chart_dim,
        dodge=False,
        legend=False,
        palette="viridis",
    )
    plt.title(f"{title_prefix} - Problematic Entities Percentage by Version")
    plt.xlabel("Release" if chart_dim == "release_step" else chart_dim.title())
    plt.ylabel("(filtered methods + classes) / (all methods + classes) [%]")
    plt.xticks(rotation=20, ha="right")
    _save_fig(out_dir / "05_method_findings_percentage_by_milestone.png")

    heat_df = (
        comparison.pivot(index="project", columns=chart_dim, values="method_findings_pct")
        .fillna(0)
    )
    if not heat_df.empty:
        if order:
            ordered_cols = [c for c in order if c in heat_df.columns] + [c for c in heat_df.columns if c not in order]
            heat_df = heat_df.reindex(columns=ordered_cols)

        # Keep chart readable on large datasets.
        top_projects = heat_df.mean(axis=1).sort_values(ascending=False).head(25).index
        heat_df = heat_df.loc[top_projects]

        plt.figure(figsize=(11, max(6, 0.35 * len(heat_df.index))))
        sns.heatmap(heat_df, annot=True, fmt=".1f", cmap="PuBuGn", cbar_kws={"label": "Percentage [%]"})
        plt.title(f"{title_prefix} - Problematic Entities Percentage by Project and Version")
        plt.xlabel("Release" if chart_dim == "release_step" else chart_dim.title())
        plt.ylabel("Project")
        _save_fig(out_dir / "06_method_findings_percentage_heatmap.png")


def generate_charts(
    df: pd.DataFrame,
    out_dir: Path,
    title_prefix: str,
    totals_df: pd.DataFrame | None = None,
    entity_df: pd.DataFrame | None = None,
) -> None:
    if df.empty:
        print(f"No method-level records found for {title_prefix}.")
        return

    sns.set_theme(style="whitegrid")

    metric_counts = df["metric_name"].value_counts().rename_axis("metric_name").reset_index(name="findings")
    plt.figure(figsize=(10, 5))
    sns.barplot(data=metric_counts, x="metric_name", y="findings", hue="metric_name", dodge=False, legend=False)
    plt.title(f"{title_prefix} - Findings by Method Metric")
    plt.xlabel("Metric")
    plt.ylabel("Findings")
    plt.xticks(rotation=20, ha="right")
    _save_fig(out_dir / "01_findings_by_metric.png")

    top_methods = (
        df.assign(method_project=df["project"] + " :: " + df["method"])
        .groupby("method_project", as_index=False)
        .size()
        .sort_values("size", ascending=False)
        .head(20)
    )
    plt.figure(figsize=(12, 8))
    sns.barplot(data=top_methods, y="method_project", x="size", hue="method_project", dodge=False, legend=False)
    plt.title(f"{title_prefix} - Top 20 Methods by Findings")
    plt.xlabel("Findings")
    plt.ylabel("Method")
    _save_fig(out_dir / "02_top_methods.png")

    top_projects = df["project"].value_counts().head(20).index
    heat_df = (
        df[df["project"].isin(top_projects)]
        .groupby(["project", "metric_name"], as_index=False)
        .size()
        .pivot(index="project", columns="metric_name", values="size")
        .fillna(0)
    )
    if not heat_df.empty:
        plt.figure(figsize=(10, max(6, 0.35 * len(heat_df.index))))
        sns.heatmap(heat_df, annot=True, fmt=".0f", cmap="YlOrRd", cbar_kws={"label": "Findings"})
        plt.title(f"{title_prefix} - Metric Density per Project (Top 20 Projects)")
        plt.xlabel("Metric")
        plt.ylabel("Project")
        _save_fig(out_dir / "03_metric_density_heatmap.png")

    numeric_df = df.dropna(subset=["metric_value"]).copy()
    if not numeric_df.empty:
        plt.figure(figsize=(11, 6))
        sns.boxplot(data=numeric_df, x="metric_name", y="metric_value")
        plt.title(f"{title_prefix} - Metric Value Distribution")
        plt.xlabel("Metric")
        plt.ylabel("Metric value")
        plt.xticks(rotation=20, ha="right")
        _save_fig(out_dir / "04_metric_value_distribution.png")

    # Findings by metric and version/milestone table
    generate_metric_by_version_table(df, out_dir, title_prefix)

    # Top methods with largest fluctuations between milestones/versions.
    generate_top_fluctuating_methods_table(df, out_dir, title_prefix)

    # Percentage comparison for milestones using total methods + classes.
    if totals_df is not None and not totals_df.empty:
        generate_method_percentage_comparison(df, totals_df, out_dir, title_prefix)

    # Aggregated TOPLIST of problematic methods/classes.
    if entity_df is not None and not entity_df.empty:
        generate_problematic_toplist(entity_df, out_dir, title_prefix)

    # Additional per-project comparisons (milestones/tags).
    generate_per_project_comparisons(df, out_dir, title_prefix)
    # Additional interactive sunburst charts.
    generate_sunburst_charts(df, out_dir, title_prefix, totals_df=totals_df, entity_df=entity_df)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate separate method-level visualizations for student and public project analyses."
    )
    parser.add_argument(
        "--student-inputs",
        nargs="*",
        default=[
            "method_analysis_results_1.json",
            "method_analysis_results_2.json",
            "method_analysis_results_3.json",
        ],
        help="Student method-level result files (workspace-relative or absolute).",
    )
    parser.add_argument(
        "--public-input",
        default="bulk_analyzer/public_method_analysis_results.json",
        help="Public method-level result file (workspace-relative or absolute).",
    )
    parser.add_argument(
        "--output-dir",
        default="bulk_analyzer/visualization/out",
        help="Output folder where student/ and public/ chart folders are created.",
    )
    return parser.parse_args()


def _resolve_paths(paths: list[str], workspace_root: Path) -> list[Path]:
    resolved = []
    for p in paths:
        path = Path(p)
        path = path if path.is_absolute() else workspace_root / path
        if path.exists():
            resolved.append(path)
        else:
            print(f"Warning: input file not found and skipped: {path}")
    return resolved


def main() -> None:
    args = parse_args()
    workspace_root = Path(__file__).resolve().parents[2]
    out_dir = (Path(args.output_dir) if Path(args.output_dir).is_absolute() else workspace_root / args.output_dir).resolve()

    student_paths = _resolve_paths(args.student_inputs, workspace_root)
    if student_paths:
        student_df = load_student_method_records(student_paths)
        student_totals_df = load_student_project_totals(student_paths)
        student_entity_df = load_student_problem_entity_records(student_paths)
        generate_charts(
            student_df,
            out_dir / "student",
            "Student Projects",
            totals_df=student_totals_df,
            entity_df=student_entity_df,
        )
        print(f"Student charts written to: {out_dir / 'student'}")
    else:
        print("No valid student method-level inputs were found.")

    public_path = Path(args.public_input)
    public_path = public_path if public_path.is_absolute() else workspace_root / public_path
    if public_path.exists():
        public_df = load_public_method_records(public_path)
        public_totals_df = load_public_project_totals(public_path)
        public_entity_df = load_public_problem_entity_records(public_path)
        generate_charts(
            public_df,
            out_dir / "public",
            "Public Projects",
            totals_df=public_totals_df,
            entity_df=public_entity_df,
        )
        print(f"Public charts written to: {out_dir / 'public'}")
    else:
        print(f"Public input not found: {public_path}")


if __name__ == "__main__":
    main()
