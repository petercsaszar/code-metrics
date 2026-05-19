using CodeMetricsAnalyzer.Analyzers;
using CodeMetricsAnalyzer.ResultExporter;
using CodeMetricsAnalyzer.ResultExporter.DTOs;
using Microsoft.Build.Locator;
using Microsoft.Build.Tasks;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.MSBuild;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Xml.Linq;

namespace CodeMetricsAnalyzer.Commands.Analyze
{
    public class AnalyzeCommand : IDisposable
    {
        private readonly AnalyzeCommandOptions _options;
        private readonly IResultExporter _resultExporter = new XmlResultExporter();
        private readonly HtmlReportGenerator _htmlReportGenerator = new HtmlReportGenerator();
        private MSBuildWorkspace? _workspace;

        public AnalyzeCommand(AnalyzeCommandOptions options)
        {
            _options = options;
        }

        public async Task<int> RunAnalysisAsync(CancellationToken cancellationToken = default)
        {
            try
            {
                await AnalyzeAsync(cancellationToken);
                return 0;
            }
            catch (WorkspaceDiagnosticsException)
            {
                WriteWorkspaceDiagnostics();
                return 1;
            }
            catch (Exception e)
            {
                // TODO better error handling/logging
                ConsoleWriteLineWithColor(ConsoleColor.Red, e.Message);
                Console.WriteLine("Try defining the MSBuild path using the --msbuild-path option.");
                return 2;
            }
        }

        private async Task AnalyzeAsync(CancellationToken cancellationToken = default)
        {
            CreateWorkspace();

            var analyzers = AnalyzerFactory.CreateAnalyzers(_options.AnalyzerConfiguration);

            var results = (await AnalyzeAsync(analyzers, cancellationToken)).ToList();

            WriteAnalysisResults(results);

            if (_options.Output is not null)
            {
                await _resultExporter.ExportResultsAsync(_options.Output, new ResultExporterArguments
                {
                    ProjectDiagnostics = results,
                    SolutionDirectory = Path.GetDirectoryName(_options.Source.FullName)
                }, cancellationToken);
            }

            if (_options.ReportOutput is not null)
            {
                ConsoleWriteLineWithColor(ConsoleColor.Cyan, $"Generating HTML report at: {_options.ReportOutput}");

                // Default history directory to reports/history if not specified
                var historyDir = _options.HistoryDirectory ?? Path.Combine(_options.ReportOutput, "history");

                await _htmlReportGenerator.GenerateReportAsync(
                    _options.ReportOutput, 
                    new ResultExporterArguments
                    {
                        ProjectDiagnostics = results,
                        SolutionDirectory = Path.GetDirectoryName(_options.Source.FullName)
                    }, 
                    historyDir,
                    cancellationToken);
                ConsoleWriteLineWithColor(ConsoleColor.Green, "HTML report generated successfully!");
            }
        }

        private async Task<IEnumerable<ProjectDiagnosticsDto>> AnalyzeAsync(ImmutableArray<DiagnosticAnalyzer> analyzers, CancellationToken cancellationToken = default)
        {
            if (_options.Source.Extension == ".slnx")
            {
                // Handle .slnx files by parsing projects manually
                return await AnalyzeSlnxFileAsync(analyzers, cancellationToken);
            }

            var isSolution = _options.Source.Extension == ".sln";
            if (isSolution)
            {
                var solution = await _workspace!.OpenSolutionAsync(_options.Source.FullName, null, cancellationToken);
                CheckForWorkspaceDiagnostics();
                return await AnalyzeSolutionAsync(solution, analyzers, cancellationToken);
            }
            else
            {
                var project = await _workspace!.OpenProjectAsync(_options.Source.FullName, null, cancellationToken);
                CheckForWorkspaceDiagnostics();
                var result = await AnalyzeProjectAsync(project, analyzers, cancellationToken);
                return [result];
            }
        }

        private async Task<IEnumerable<ProjectDiagnosticsDto>> AnalyzeSlnxFileAsync(ImmutableArray<DiagnosticAnalyzer> analyzers, CancellationToken cancellationToken)
        {
            ConsoleWriteLineWithColor(ConsoleColor.Cyan, "Parsing .slnx file...");

            var projectPaths = ParseSlnxFile(_options.Source.FullName);
            var solutionDir = Path.GetDirectoryName(_options.Source.FullName) ?? throw new Exception("Unable to determine solution directory.");

            ConsoleWriteLineWithColor(ConsoleColor.Cyan, $"Found {projectPaths.Count} project(s) in solution.");

            var results = new List<ProjectDiagnosticsDto>();

            foreach (var projectPath in projectPaths)
            {
                cancellationToken.ThrowIfCancellationRequested();

                var fullProjectPath = Path.IsPathRooted(projectPath) 
                    ? projectPath 
                    : Path.GetFullPath(Path.Combine(solutionDir, projectPath));

                if (!File.Exists(fullProjectPath))
                {
                    ConsoleWriteLineWithColor(ConsoleColor.Yellow, $"Warning: Project file not found: {fullProjectPath}");
                    continue;
                }

                try
                {
                    var project = await _workspace!.OpenProjectAsync(fullProjectPath, null, cancellationToken);
                    CheckForWorkspaceDiagnostics();

                    if (project.Language != LanguageNames.CSharp)
                    {
                        ConsoleWriteLineWithColor(ConsoleColor.Yellow, $"Skipping non-C# project: {project.Name}");
                        continue;
                    }

                    var result = await AnalyzeProjectAsync(project, analyzers, cancellationToken);
                    results.Add(result);

                    ConsoleWriteLineWithColor(ConsoleColor.Green, $"Analyzed: {project.Name}");
                }
                catch (Exception ex)
                {
                    ConsoleWriteLineWithColor(ConsoleColor.Yellow, $"Warning: Failed to analyze project {fullProjectPath}: {ex.Message}");
                }
            }

            return results;
        }

        private static List<string> ParseSlnxFile(string slnxPath)
        {
            var projectPaths = new List<string>();

            try
            {
                var xml = System.Xml.Linq.XDocument.Load(slnxPath);
                var ns = xml.Root?.Name.Namespace ?? System.Xml.Linq.XNamespace.None;

                // Look for Project elements with Path attribute
                var projects = xml.Descendants(ns + "Project")
                    .Select(p => p.Attribute("Path")?.Value)
                    .Where(path => !string.IsNullOrWhiteSpace(path) && 
                                   (path!.EndsWith(".csproj", StringComparison.OrdinalIgnoreCase) ||
                                    path.EndsWith(".vbproj", StringComparison.OrdinalIgnoreCase) ||
                                    path.EndsWith(".fsproj", StringComparison.OrdinalIgnoreCase)))
                    .Select(path => path!);

                projectPaths.AddRange(projects);
            }
            catch (Exception ex)
            {
                throw new Exception($"Failed to parse .slnx file: {ex.Message}", ex);
            }

            return projectPaths;
        }

        private void CreateWorkspace()
        {
            // TODO export to config
            var properties = new Dictionary<string, string>
            {
                // ["DesignTimeBuild"] = "true",
                ["BuildingInsideVisualStudio"] = "false",
                ["RunAnalyzers"] = "false",
                ["SkipUnsupportedTargetFrameworks"] = "true",

                ["SuppressTfmSupportBuildWarnings"] = "true",
                ["TreatWarningsAsErrors"] = "false",
                ["CheckEolTargetFramework"] = "false",

                ["RunAnalyzers"] = "false",
                ["NuGetAudit"] = "false",
                ["WarningsAsErrors"] = "",
                ["WarningsNotAsErrors"] = "NU1902;NU1903",
                ["NoWarn"] = "NU1902;NU1903",
            };

            Environment.SetEnvironmentVariable("DOTNET_ROLL_FORWARD", "latestMajor");

            
            if (!MSBuildLocator.IsRegistered)
            {
                if (_options.MSBuildPath is not null)
                {
                    MSBuildLocator.RegisterMSBuildPath(_options.MSBuildPath);
                }
                else
                {
                    MSBuildLocator.RegisterDefaults();
                }
            }
            _workspace = MSBuildWorkspace.Create(properties);
        }

        private void CheckForWorkspaceDiagnostics()
        {
            foreach (var diagnostic in _workspace!.Diagnostics)
            {
                if (diagnostic.Message.Contains("is not associated with a language",
                                                StringComparison.OrdinalIgnoreCase) || 
                                               (diagnostic.Message.Contains("has a known", StringComparison.OrdinalIgnoreCase) &&
                                                diagnostic.Message.Contains("vulnerability", StringComparison.OrdinalIgnoreCase)))
                {
                    ConsoleWriteLineWithColor(ConsoleColor.Yellow, $"Warning: {diagnostic.Message}");
                    continue;
                }

               
                if (diagnostic.Kind == WorkspaceDiagnosticKind.Failure)
                {
                    throw new WorkspaceDiagnosticsException();
                }
            }
        }

        private void WriteWorkspaceDiagnostics()
        {
            if (_workspace!.Diagnostics.Count > 0)
            {
                ConsoleWriteLineWithColor(ConsoleColor.Red, "Error opening solution/project.");
                Console.WriteLine("Workspace diagnostics:");
                foreach (var diagnostic in _workspace.Diagnostics)
                {
                    Console.WriteLine($"\t- {diagnostic.Kind}: {diagnostic.Message}");
                }
            }
        }

        private static async Task<IEnumerable<ProjectDiagnosticsDto>> AnalyzeSolutionAsync(Solution solution, ImmutableArray<DiagnosticAnalyzer> analyzers, CancellationToken cancellationToken = default)
        {
            var projectIds = solution
                .GetProjectDependencyGraph()
                .GetTopologicallySortedProjects(cancellationToken)
                .ToImmutableArray();

            var results = new List<ProjectDiagnosticsDto>();

            foreach (var projectId in projectIds)
            {
                cancellationToken.ThrowIfCancellationRequested();

                var project = solution.GetProject(projectId);
                if (project == null)
                {
                    throw new InvalidOperationException($"Project with id '{projectId}' was not found in the solution.");
                }

                if (project.Language != LanguageNames.CSharp)
                    continue;

                var result = await AnalyzeProjectAsync(project, analyzers, cancellationToken);

                results.Add(result);
            }

            return results;
        }

        private static async Task<ProjectDiagnosticsDto> AnalyzeProjectAsync(Project project, ImmutableArray<DiagnosticAnalyzer> analyzers, CancellationToken cancellationToken = default)
        {
            var compilation = await project.GetCompilationAsync(cancellationToken);
            if (compilation == null)
            {
                throw new InvalidOperationException($"Could not obtain compilation for project '{project.Name}'.");
            }

            var compilationWithAnalyzers = new CompilationWithAnalyzers(compilation, analyzers, null as AnalyzerOptions);

            var diagnostics = await compilationWithAnalyzers.GetAnalyzerDiagnosticsAsync(analyzers, cancellationToken);

            return new ProjectDiagnosticsDto
            {
                Name = project.Name,
                FilePath = project.FilePath ?? throw new Exception("Project's FilePath property is null."),
                Diagnostics = diagnostics.Select(diagnostic => new DiagnosticDto
                {
                    Id = diagnostic.Id,
                    Severity = diagnostic.Severity.ToString(),
                    Title = diagnostic.Descriptor.Title.ToString(),
                    Description = diagnostic.Descriptor.Description.ToString(),
                    Message = diagnostic.GetMessage(),
                    FilePath = diagnostic.Location.SourceTree?.FilePath ?? string.Empty,
                    Location = new LocationDto
                    {
                        Line = diagnostic.Location.GetMappedLineSpan().StartLinePosition.Line + 1,
                        Character = diagnostic.Location.GetMappedLineSpan().StartLinePosition.Character + 1
                    }
                }).ToList()
            };
        }

        private static void WriteAnalysisResults(IEnumerable<ProjectDiagnosticsDto> results)
        {
            ConsoleWriteLineWithColor(ConsoleColor.Cyan, "Analysis results:");

            var diagnostics = results
                .SelectMany(projectDiagnostic => projectDiagnostic.Diagnostics)
                .GroupBy(diagnostic => diagnostic.Id, diagnostic => diagnostic)
                .ToDictionary(group => group.Key, group => group.ToList());

            int diagnosticCount = diagnostics.Sum(kvp => kvp.Value.Count);
            if (diagnosticCount > 0)
            {
                int maxCountLength = Math.Max(diagnosticCount.ToString().Length, diagnostics.Max(kvp => kvp.Value.Count.ToString().Length));
                int maxIdLength = diagnostics.Max(kvp => kvp.Key.Length);

                foreach (var kvp in diagnostics.OrderBy(kvp => kvp.Key))
                {
                    Console.WriteLine($"{kvp.Value.Count.ToString().PadLeft(maxCountLength)} {kvp.Value[0].Id.PadRight(maxIdLength)} {kvp.Value[0].Title}");
                }
            }

            Console.WriteLine();

            ConsoleWriteLineWithColor(ConsoleColor.Green, $"{diagnosticCount} {((diagnosticCount == 1) ? "diagnostic" : "diagnostics")} found");
        }

        public void Dispose()
        {
            _workspace?.Dispose();
        }

        private static void ConsoleWriteLineWithColor(ConsoleColor color, string message)
        {
            var original = Console.ForegroundColor;
            Console.ForegroundColor = color;
            Console.WriteLine(message);
            Console.ForegroundColor = original;
        }
    }
}
