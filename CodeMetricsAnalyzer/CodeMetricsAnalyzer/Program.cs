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

            var options = new AnalyzeCommandOptions
            {
                Source = source,
                Output = output
            };

            var analyzeCommand = new AnalyzeCommand(options);
            context.ExitCode = await analyzeCommand.RunAnalysisAsync(cancellationToken);
        });

        return command;
    }
}
