using System.Diagnostics;

namespace CodeMetricsAnalyzer.ResultExporter;

public class GitInfoProvider
{
    public async Task<GitInfo> GetCurrentGitInfoAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var commitHash = await RunGitCommandAsync("rev-parse HEAD", cancellationToken);
            var commitMessage = await RunGitCommandAsync("log -1 --pretty=%B", cancellationToken);
            var commitAuthor = await RunGitCommandAsync("log -1 --pretty=%an", cancellationToken);
            var commitDateStr = await RunGitCommandAsync("log -1 --pretty=%cI", cancellationToken);
            
            return new GitInfo
            {
                CommitHash = commitHash?.Trim() ?? "unknown",
                CommitMessage = commitMessage?.Trim() ?? "unknown",
                CommitAuthor = commitAuthor?.Trim() ?? "unknown",
                CommitDate = DateTime.TryParse(commitDateStr, out var date) ? date : DateTime.Now
            };
        }
        catch
        {
            return new GitInfo
            {
                CommitHash = Environment.GetEnvironmentVariable("CI_COMMIT_SHA") ?? "unknown",
                CommitMessage = Environment.GetEnvironmentVariable("CI_COMMIT_MESSAGE") ?? "unknown",
                CommitAuthor = Environment.GetEnvironmentVariable("CI_COMMIT_AUTHOR") ?? "unknown",
                CommitDate = DateTime.Now
            };
        }
    }
    
    private async Task<string?> RunGitCommandAsync(string arguments, CancellationToken cancellationToken)
    {
        try
        {
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "git",
                    Arguments = arguments,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                }
            };
            
            process.Start();
            var output = await process.StandardOutput.ReadToEndAsync(cancellationToken);
            await process.WaitForExitAsync(cancellationToken);
            
            return process.ExitCode == 0 ? output : null;
        }
        catch
        {
            return null;
        }
    }
}

public class GitInfo
{
    public required string CommitHash { get; set; }
    public required string CommitMessage { get; set; }
    public required string CommitAuthor { get; set; }
    public required DateTime CommitDate { get; set; }
}
