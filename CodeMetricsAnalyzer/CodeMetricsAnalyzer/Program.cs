using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers;
using System.CommandLine;
using System.CommandLine.Invocation;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer;

public class Program
{
    public static async Task Main(string[] args)
    {
        var rootCommand = new RootCommand
        {
            CreateAnalyzeCommand()
        };

        await rootCommand.InvokeAsync(args);
    }

    private static Command CreateAnalyzeCommand()
    {
        var sourceArgument = new Argument<FileInfo>(
            name: "source",
            description: "C# project (.csproj) or solution (.sln) to analyze."
        );
        sourceArgument.AddValidator(result =>
        {
            var source = result.GetValueForArgument(sourceArgument);
            if (source == null || !source.Exists)
            {
                result.ErrorMessage = "The provided source path is invalid.";
                return;
            }

            if (source.Extension != ".sln" && source.Extension != ".csproj")
            {
                result.ErrorMessage = "The provided source file must be a project (.csproj) or solution (.sln).";
            }
        });

        var outputOption = new Option<string?>(
            name: "--output",
            description: "Path to save analysis results (optional)."
        );

        var command = new Command("analyze", "Runs the Bumpy Road Analyzer on a solution or project.")
        {
            sourceArgument,
            outputOption
        };

        command.SetHandler(async (InvocationContext context) =>
        {
            var cancellationToken = context.GetCancellationToken();
            var source = context.ParseResult.GetValueForArgument(sourceArgument);
            var outputPath = context.ParseResult.GetValueForOption(outputOption);


            // Run the existing Bumpy Road Analyzer
            var analyzer = new BumpyRoadAnalyzer();
            var diagnostics = await RunAnalyzerOnProject(source.FullName, analyzer, cancellationToken);

            if (!string.IsNullOrEmpty(outputPath))
            {
                await File.WriteAllTextAsync(outputPath, diagnostics, Encoding.UTF8, cancellationToken);
                Console.WriteLine($"Analysis results saved to {outputPath}");
            }
            else
            {
                Console.WriteLine(diagnostics);
            }

            context.ExitCode = 0;
        });

        return command;
    }

    private static async Task<string> RunAnalyzerOnProject(string sourcePath, BumpyRoadAnalyzer analyzer, CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"Running Bumpy Road Analysis on: {sourcePath}");

        ImmutableArray<DiagnosticAnalyzer> analyzers = [analyzer];

        var workspace = Microsoft.CodeAnalysis.MSBuild.MSBuildWorkspace.Create();
        var solution = workspace.OpenSolutionAsync(sourcePath, cancellationToken: cancellationToken).Result;

        var results = new List<string>();

        foreach (var project in solution.Projects)
        {
            var compilation = await project.GetCompilationAsync(cancellationToken);

            if (compilation == null)
            {
                throw new Exception();
            }

            var compilationWithAnalyzers = new CompilationWithAnalyzers(compilation, analyzers, null as AnalyzerOptions);

            Diagnostic diagnostic = null;

        }

        Console.WriteLine("Analysis complete.");
        return string.Join("\n", results);
    }
}
