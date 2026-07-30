# project_graph
<!-- dense, machine-scannable. no prose. update on structural change. -->

## modules
CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj | type=exe,dotnet-tool | pkgid=ELTE.FI.CodeMetricsAnalyzer | toolcmd=CodeMetricsAnalyzer | tfm=net8.0 | entry=Program.cs | deps=[Analyzers,Commands]
CodeMetricsAnalyzer/CodeMetricsAnalyzer.Commands.csproj | type=lib | tfm=net8.0 | entry=Analyze/AnalyzeCommand.cs | deps=[Analyzers,ResultExporter] | pkgs=[Microsoft.Build.Locator,Microsoft.CodeAnalysis.CSharp.Workspaces,Microsoft.CodeAnalysis.Workspaces.MSBuild]
CodeMetricsAnalyzer/CodeMetricsAnalyzer.Analyzers.csproj | type=lib(roslyn-analyzers) | tfm=net8.0 | entry=AnalyzerFactory.cs | deps=[] | exports=[BumpyRoadAnalyzer,ClassCouplingAnalyzer,CyclomaticComplexityAnalyzer,FunctionParameterCountAnalyzer,LCOM4Analyzer,LCOM5Analyzer,MaintainabilityIndexAnalyzer]
CodeMetricsAnalyzer/CodeMetricsAnalyzer.ResultExporter.csproj | type=lib | tfm=net8.0 | entry=[XmlResultExporter.cs,HtmlReportGenerator.cs] | deps=[] | exports=[IResultExporter,XmlResultExporter,HtmlReportGenerator,GitInfoProvider,MetricChartHelper]
CodeMetricsAnalyzer/CodeMetricsAnalyzer.Analyzers.Tests.csproj | type=test(xunit-style) | deps=[Analyzers] | helper=Helpers/RoslynTestHelper.cs

bulk_analyzer/ | type=python-package(top-level,import-as=bulk_analyzer) | entrypoints=[analyzer.py,latest_snapshot_analyzer.py,public_project_analyzer.py,html_report_generator.py,student_container_analyzer.py,container_runner.py,threshold_analyzer.py,method_analyzer.py,milestone_commit_finder.py,dotnet_environment.py]
bulk_analyzer/visualization/ | type=notebooks | consumes=analysis_results*.json,method_analysis_results*.json

docker/ | Dockerfile(linux,no-unity-by-default) Dockerfile.windows(windows-containers) Dockerfile.dotnet(base) entrypoint.sh(mode-switch) scripts/run_public_analysis.sh(guard-rail,exits1,tells-user-to-run-on-host)

## diagnostic_ids (CodeMetricsAnalyzer.Analyzers/Diagnostics/DiagnosticIdentifiers.cs)
CMA0001=BumpyRoad | config=BumpyRoadAnalysisConfiguration{BumpynessThreshold=2}
CMA0002=FunctionParameterCount | config=FunctionParameterCountAnalysisConfiguration{ParameterCountThreshold=4}
CMA0003=LCOM4 | config=LCOM4AnalysisConfiguration{CohesionThreshold=4,MinimumMethodCount=2,MinimumFieldCount=1}
CMA0004=LCOM5 | config=LCOM5AnalysisConfiguration{CohesionThreshold=0.5,MinimumMethodCount=2,MinimumMemberCount(alias MinimumFieldCount)=1}
CMA0005=MaintainabilityIndex | config=MaintainabilityIndexAnalysisConfiguration{MinimumMaintainabilityIndex=65}
CMA0006=CyclomaticComplexity | config=CyclomaticComplexityAnalysisConfiguration{MaximumComplexity=6}
CMA0007=ClassCoupling | config=ClassCouplingAnalysisConfiguration{MaximumClassCoupling=15}
note: no per-analyzer Enabled flag exists; all 7 always run. root=AnalyzerConfiguration.cs aggregates all 7 configs, bound from appsettings.json.
to-add-new-analyzer: DiagnosticIdentifiers.cs(id) + DiagnosticDescriptors.cs(descriptor) + Configurations/*.cs(config class) + AnalyzerConfiguration.cs(property) + AnalyzerFactory.cs(wire) + AnalyzerReleases.Unshipped.md(RS2000 entry)

## data_flow
GitLab API --HTTP(PRIVATE-TOKEN header)--> bulk_analyzer.milestone_commit_finder --finds--> milestone commits (Levenshtein-fuzzy name match, requires due date)
  --> bulk_analyzer.analyzer clones via gitpython --> checkout commit --> dotnet_environment.ensure_dotnet_environment --> build .sln (dotnet build -p:EnableWindowsTargeting=true)
  --> invoke CodeMetricsAnalyzer CLI (`dotnet run --project Commands... analyze <sln>` or bundled DLL at $BUNDLED_ANALYZER_PATH) --> AnalyzeCommand.cs
  --> Analyzers run over Roslyn workspace --> diagnostics --> ResultExporter.XmlResultExporter(--output) + HtmlReportGenerator(--report-output, --history-dir)
  --> JSON aggregation in bulk_analyzer (analysis_results_N.json) + HTML reports on disk
ALT PATH: bulk_analyzer.latest_snapshot_analyzer skips milestone_commit_finder, checks out HEAD of default branch directly, same downstream analyzer invocation. selected via docker ANALYSIS_MODE=latest_snapshot (see docker/entrypoint.sh).
ALT PATH (Unity repos): bulk_analyzer detects ProjectSettings/ProjectVersion.txt under repo -> generates .sln from Assets/*.asmdef via pure-Python generator (_build_unity_csproj/_build_unity_sln in latest_snapshot_analyzer.py, mirrored in analyzer.py) -> same analyzer invocation. Optional: real Unity editor sync via UNITY_SYNC_WITH_EDITOR=1 + UNITY_LICENSE_PATH, falls back to Python generator on failure.
git metadata for reports: git CLI in repo, else CI_COMMIT_SHA/CI_COMMIT_MESSAGE/CI_COMMIT_AUTHOR env vars (GitInfoProvider.cs).
CodeChecker export (optional, method-level mode only): config.yml codechecker.enabled -> writes custom_metrics.plist/.json under codechecker_reports/<project>_<commit>/.

## config_files
bulk_analyzer/config.yml | GITIGNORED (secrets: gitlab.token) | template=bulk_analyzer/config.example.yml | keys=gitlab.{url,token,group_id,subgroup_id,milestone_keywords} project.clone_dir analyzer.{solution_dir,project_dir,msbuild_dir,project_file,unity_path,unity_version,cloc_path} public_analyzer.{repository_list,clone_dir,concurrency,output_file} docker.{image,os} codechecker.{enabled,export_dir,export_plist,export_json}
CodeMetricsAnalyzer/CodeMetricsAnalyzer/appsettings.json | TRACKED (no secrets) | bound to AnalyzerConfiguration via Microsoft.Extensions.Configuration

## docs_map
README.md(root,master/overview) -> docs/QUICKSTART.md(.NET CLI+config+CI-examples) docs/DOCKER_README.md(docker deep-dive) CodeMetricsAnalyzer/README.md(module) bulk_analyzer/README.md(module) .gitlab-ci.example.yml(copy-paste template, not linted as part of docs audit)

## known_gaps (as of 2026-07-30 audit — verify still true before relying on)
- no lint/format/test config for bulk_analyzer/ (no pyproject.toml, .flake8, pytest.ini)
- CodeMetricsAnalyzer package not published to any public/private NuGet feed (no CI publish workflow found; no .github/ dir exists)
- latest_snapshot_analyzer.py added 2026-07-30 (commit 76043fa) — check `git log --oneline -- bulk_analyzer/latest_snapshot_analyzer.py` before assuming doc coverage is still accurate
