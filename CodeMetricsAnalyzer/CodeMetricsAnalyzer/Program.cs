using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers;
using System.CommandLine;
using System.CommandLine.Invocation;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Globalization;
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
        CultureInfo.DefaultThreadCurrentCulture = new CultureInfo("en-US");
        CultureInfo.DefaultThreadCurrentUICulture = new CultureInfo("en-US");
        
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

            if (source.Extension != ".sln" && source.Extension != ".slnx" && source.Extension != ".csproj")
            {
                result.ErrorMessage = "The provided source file is not a project or solution.";
            }
        });

        var outputOption = new Option<string?>(
            name: "--output",
            description: "Output file path."
        );

        var reportOutputOption = new Option<string?>(
            name: "--report-output",
            description: "Report output folder path."
        );

        var historyDirectoryOption = new Option<string?>(
            name: "--history-dir",
            description: "Directory path for storing historical metrics. Defaults to '<report-output>/history' if report output is specified."
        );

        var msbuildOption = new Option<string?>(
            name: "--msbuild-path",
            description: "Path to MSBuild installation to use."
        );
        msbuildOption.AddValidator(result =>
        {
            var location = result.GetValueForOption(msbuildOption);
            if (location == null || !System.IO.Directory.Exists(location))
            {
                result.ErrorMessage = "The provided MSBuild location is invalid.";
                return;
            }
        });

        var command = new Command("analyze", "Performs code metrics analysis on the provided project or solution.")
        {
            sourceArgument,
            outputOption,
            reportOutputOption,
            historyDirectoryOption,
            msbuildOption
        };

        command.SetHandler(async (InvocationContext context) =>
        {
            var cancellationToken = context.GetCancellationToken();

            var source = context.ParseResult.GetValueForArgument(sourceArgument);
            var output = context.ParseResult.GetValueForOption(outputOption);
            var reportOutput = context.ParseResult.GetValueForOption(reportOutputOption);
            var historyDirectory = context.ParseResult.GetValueForOption(historyDirectoryOption);
            var msbuildPath = context.ParseResult.GetValueForOption(msbuildOption);
            var analyzerConfiguration = await LoadAppSettingsAsync(cancellationToken);

            var options = new AnalyzeCommandOptions
            {
                Source = source,
                Output = output,
                ReportOutput = reportOutput,
                HistoryDirectory = historyDirectory,
                MSBuildPath = msbuildPath,
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
