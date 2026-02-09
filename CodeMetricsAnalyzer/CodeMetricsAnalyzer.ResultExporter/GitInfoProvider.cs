using System.Diagnostics;

namespace CodeMetricsAnalyzer.ResultExporter;

public class GitInfoProvider
{
    public async Task<GitInfo> GetCurrentGitInfoAsync(string? workingDirectory = null, CancellationToken cancellationToken = default)
    {
        try
        {
            // Find the Git repository root starting from the working directory
            var gitRepoDirectory = FindGitRepository(workingDirectory);
            
            var commitHash = await RunGitCommandAsync("rev-parse HEAD", gitRepoDirectory, cancellationToken);
            var commitMessage = await RunGitCommandAsync("log -1 --pretty=%B", gitRepoDirectory, cancellationToken);
            var commitAuthor = await RunGitCommandAsync("log -1 --pretty=%an", gitRepoDirectory, cancellationToken);
            var commitDateStr = await RunGitCommandAsync("log -1 --pretty=%cI", gitRepoDirectory, cancellationToken);
            
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
    
    private string? FindGitRepository(string? startDirectory)
    {
        try
        {
            var directory = startDirectory ?? Directory.GetCurrentDirectory();
            
            // Ensure we have a valid directory
            if (!Directory.Exists(directory))
            {
                return Directory.GetCurrentDirectory();
            }
            
            var currentDir = new DirectoryInfo(directory);
            
            // Walk up the directory tree looking for .git directory
            while (currentDir != null)
            {
                var gitDir = Path.Combine(currentDir.FullName, ".git");
                
                // Check if .git exists (either as directory or file for submodules/worktrees)
                if (Directory.Exists(gitDir) || File.Exists(gitDir))
                {
                    return currentDir.FullName;
                }
                
                currentDir = currentDir.Parent;
            }
            
            // If no .git found, return the starting directory or current directory
            return directory;
        }
        catch
        {
            return Directory.GetCurrentDirectory();
        }
    }
    
    private async Task<string?> RunGitCommandAsync(string arguments, string? workingDirectory, CancellationToken cancellationToken)
    {
        try
        {
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "git",
                    Arguments = arguments,
                    WorkingDirectory = workingDirectory ?? Directory.GetCurrentDirectory(),
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
