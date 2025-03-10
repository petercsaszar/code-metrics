using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers;
using System.CommandLine;
using System.CommandLine.Invocation;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;
using System.Runtime.InteropServices;
using CodeMetricsAnalyzer.Commands.Analyze;
using CodeMetricsAnalyzer.Analyzers.Configurations;

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
            description: "Project or solution to analyze."
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
                result.ErrorMessage = "The provided source file is not a project or solution.";
            }
        });

        var outputOption = new Option<string?>(
            name: "--output",
            description: "Output file path."
        );

        var command = new Command("analyze", "Performs code metrics analysis on the provided project or solution.")
        {
            sourceArgument,
            outputOption
        };

        command.SetHandler(async (InvocationContext context) =>
        {
            var cancellationToken = context.GetCancellationToken();

            var source = context.ParseResult.GetValueForArgument(sourceArgument);
            var output = context.ParseResult.GetValueForOption(outputOption);
            var analyzerConfiguration = await LoadAppSettingsAsync(cancellationToken);

            var options = new AnalyzeCommandOptions
            {
                Source = source,
                Output = output,
                AnalyzerConfiguration = analyzerConfiguration
            };

            var analyzeCommand = new AnalyzeCommand(options);
            context.ExitCode = await analyzeCommand.RunAnalysisAsync(cancellationToken);
        });

        return command;
    }

    private static async Task<AnalyzerConfiguration> LoadAppSettingsAsync(CancellationToken cancellationToken = default)
    {
        var directory = new FileInfo(Assembly.GetExecutingAssembly().Location).Directory?.FullName;
        if (directory is null)
        {
            throw new Exception("Error determining executing assembly directory.");
        }

        var path = Path.Combine(directory, "appsettings.json");
        var json = await File.ReadAllTextAsync(path, cancellationToken);
        var appSettings = JsonSerializer.Deserialize<AnalyzerConfiguration>(json);
        if (appSettings is null)
        {
            throw new Exception("Error loading appsettings.json file.");
        }

        return appSettings;
    }
}
