using CodeMetricsAnalyzer.ResultExporter;
using CodeMetricsAnalyzer.ResultExporter.DTOs;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.MSBuild;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using CodeMetricsAnalyzer.Analyzers;
using Microsoft.Build.Locator;

namespace CodeMetricsAnalyzer.Commands.Analyze
{
    public class AnalyzeCommand
    {
        private readonly AnalyzeCommandOptions _options;
        private readonly IResultExporter _resultExporter = new XmlResultExporter();
        private MSBuildWorkspace _workspace;

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
            catch
            {
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
                }, cancellationToken);
            }
        }

        private async Task<IEnumerable<ProjectDiagnosticsDto>> AnalyzeAsync(ImmutableArray<DiagnosticAnalyzer> analyzers, CancellationToken cancellationToken = default)
        {
            var isSolution = _options.Source.Extension == ".sln";
            if (isSolution)
            {
                var solution = await _workspace.OpenSolutionAsync(_options.Source.FullName, null, cancellationToken);
                CheckForWorkspaceDiagnostics();
                return await AnalyzeSolutionAsync(solution, analyzers, cancellationToken);
            }
            else
            {
                var project = await _workspace.OpenProjectAsync(_options.Source.FullName, null, cancellationToken);
                CheckForWorkspaceDiagnostics();
                var result = await AnalyzeProjectAsync(project, analyzers, cancellationToken);
                return [result];
            }
        }

        private void CreateWorkspace()
        {
            MSBuildLocator.RegisterDefaults();

            _workspace = MSBuildWorkspace.Create();
        }

        private void CheckForWorkspaceDiagnostics()
        {
            if (_workspace.Diagnostics.Any(diagnostic => diagnostic.Kind == WorkspaceDiagnosticKind.Failure))
            {
                throw new WorkspaceDiagnosticsException();
            }
        }

        private void WriteWorkspaceDiagnostics()
        {
            if (_workspace.Diagnostics.Count > 0)
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
                    throw new Exception();
                }

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
                throw new Exception();
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

        private static void ConsoleWriteLineWithColor(ConsoleColor color, string message)
        {
            Console.ForegroundColor = color;
            Console.WriteLine(message);
            Console.ForegroundColor = ConsoleColor.White;
        }
    }
}
