# CLAUDE.md — AI behavior contract for this repo

Dense, machine-facing sibling docs: [`.claude/memory/project_graph.md`](memory/project_graph.md) (module/dependency map), [`.claude/memory/decisions.log`](memory/decisions.log) (JSONL decision log). Human docs live in the root [`README.md`](../README.md) and [`docs/`](../docs/).

## Architecture boundaries — do not violate

- **`bulk_analyzer/` is a top-level importable Python package, not relocatable.** Every invocation in docs/Docker is `python -m bulk_analyzer.<module>` run from the repo root, and `docker/Dockerfile*` `COPY`/`WORKDIR`/`PYTHONPATH` all assume this path. Do not move it under `src/` or similar.
- **`CodeMetricsAnalyzer/` is a .NET solution with relative `ProjectReference`/`.sln` paths.** Don't restructure directories inside it without updating `CodeMetricsAnalyzer.sln` and every `.csproj` reference.
- **Module READMEs are canonical, not duplicated content**: `CodeMetricsAnalyzer/README.md` and `bulk_analyzer/README.md` document their own module; the root `README.md` is the entry point/overview and links out — don't re-merge them.
- **`docs/QUICKSTART.md` and `docs/DOCKER_README.md`** hold the deep-dive human docs (CLI flags, config schema, CI examples, Docker/Unity workflows). Keep new detailed usage docs there, not in the root README.

## Key conventions

- **Diagnostic IDs are centralized**: `CodeMetricsAnalyzer.Analyzers/Diagnostics/DiagnosticIdentifiers.cs` (CMA0001–CMA0007) + `DiagnosticDescriptors.cs`. A new analyzer needs: an ID constant, a descriptor, a `*AnalysisConfiguration` class, a property on `AnalyzerConfiguration.cs`, wiring in `AnalyzerFactory.cs`, and a release-tracking entry in `AnalyzerReleases.Unshipped.md` (Roslyn RS2000 convention — do not skip this or the analyzer package fails its own build-time checks).
- **`appsettings.json` keys must match `*AnalysisConfiguration` property names exactly** (bound via `Microsoft.Extensions.Configuration`). There is currently **no per-analyzer enable/disable flag** — all seven are always on; only thresholds are configurable. (Docs previously showed a fake `"Enabled": true` key — fixed 2026-07-30, don't reintroduce it without adding the actual feature first.)
- **Package id ≠ tool command name.** `CodeMetricsAnalyzer/CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj` sets `PackageId=ELTE.FI.CodeMetricsAnalyzer`, `ToolCommandName=CodeMetricsAnalyzer`, `PackageOutputPath=./nupkg`. `dotnet tool install` needs the **PackageId**; the installed executable is invoked as `CodeMetricsAnalyzer`. The package is not published to any public feed as of 2026-07-30 — "install as global tool" docs must say "build from source" unless a publish pipeline is added.
- **CI git metadata**: `GitInfoProvider.cs` reads `CI_COMMIT_SHA` / `CI_COMMIT_MESSAGE` / `CI_COMMIT_AUTHOR` env vars as a fallback when not run inside a git repo — these are the real, load-bearing var names, not placeholders.
- **Docker entrypoint mode switch**: `docker/entrypoint.sh` reads `ANALYSIS_MODE` (`milestone` default, or `latest_snapshot`) to choose between `bulk_analyzer.analyzer` and `bulk_analyzer.latest_snapshot_analyzer`.
- **Secrets**: `GITLAB_TOKEN` must never be baked into the image or committed in `config.yml` (root `.gitignore` excludes `config.yml`; only `bulk_analyzer/config.example.yml` is tracked). Token is env-var-only by design in `entrypoint.sh`.

## Build, test, run commands (exact)

```bash
# .NET — build / test / pack
dotnet build CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln
dotnet test CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln
dotnet pack CodeMetricsAnalyzer/CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj --configuration Release
# -> nupkg at CodeMetricsAnalyzer/CodeMetricsAnalyzer/nupkg/

# Python — no formal lint/format/test tooling is configured in this repo
# (no pyproject.toml, .flake8, or pytest.ini exist) — don't invent one silently;
# ask the user before adding linting/test infra to bulk_analyzer/.
pip install -r bulk_analyzer/requirements.txt
python -m bulk_analyzer.analyzer                       # milestone-based GitLab analysis
python -m bulk_analyzer.latest_snapshot_analyzer        # HEAD-of-default-branch analysis
python bulk_analyzer/public_project_analyzer.py         # public/open-source repos
python -m bulk_analyzer.html_report_generator            # standalone bulk HTML report

# Docker
docker build -f docker/Dockerfile -t code-metrics-analyzer .
docker build -f docker/Dockerfile.windows -t code-metrics-analyzer:windows .
```

## Non-negotiable rules

- Never commit `bulk_analyzer/config.yml` (real GitLab tokens live only in env vars / the gitignored local file) — only `config.example.yml` is tracked.
- Keep `docs/QUICKSTART.md`'s config example and metric-threshold table in sync with `CodeMetricsAnalyzer.Analyzers/Configurations/*.cs` — they drifted out of sync once already (2026-07-30 audit); don't let it happen silently again.
- When adding a new Roslyn diagnostic, update `AnalyzerReleases.Unshipped.md` in the same change — Roslyn's own analyzer-release-tracking rule (RS2000-family) will otherwise flag the build.
- Don't move `bulk_analyzer/` or restructure `CodeMetricsAnalyzer/`'s project layout without updating every path reference in `docker/Dockerfile*`, `docker/entrypoint.sh`, and the `.sln`/`.csproj` files (see Architecture boundaries above).
