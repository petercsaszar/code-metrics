using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;
using System.Collections.Immutable;

namespace CodeMetricsAnalyzer.Analyzers.Tests.Helpers;

internal static class RoslynTestHelper
{
    private static readonly IReadOnlyList<MetadataReference> CommonReferences =
        AppDomain.CurrentDomain.GetAssemblies()
            .Where(a => !a.IsDynamic && !string.IsNullOrWhiteSpace(a.Location))
            .Select(a => MetadataReference.CreateFromFile(a.Location))
            .Cast<MetadataReference>()
            .ToList();

    public static CSharpCompilation CreateCompilation(string source)
    {
        var tree = CSharpSyntaxTree.ParseText(source);
        return CSharpCompilation.Create(
            "TestAssembly",
            new[] { tree },
            CommonReferences,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
    }

    /// <summary>
    /// Returns the root IOperation for the first method in <paramref name="source"/>,
    /// using the same fallback chain as MethodAnalyzer.GetMemberOperation.
    /// </summary>
    public static (IOperation? rootOp, MethodDeclarationSyntax methodNode) GetFirstMethodOperation(string source)
    {
        var compilation = CreateCompilation(source);
        var tree = compilation.SyntaxTrees.First();
        var model = compilation.GetSemanticModel(tree);
        var method = tree.GetRoot().DescendantNodes()
            .OfType<MethodDeclarationSyntax>().First();

        var bodyOp = model.GetOperation(method, CancellationToken.None) as IMethodBodyOperation;
        IOperation? rootOp = bodyOp?.BlockBody ?? (IOperation?)bodyOp?.ExpressionBody;

        if (rootOp == null && method.Body != null)
            rootOp = model.GetOperation(method.Body, CancellationToken.None);
        if (rootOp == null && method.ExpressionBody?.Expression != null)
            rootOp = model.GetOperation(method.ExpressionBody.Expression, CancellationToken.None);

        return (rootOp, method);
    }

    public static async Task<ImmutableArray<Diagnostic>> GetAnalyzerDiagnosticsAsync(
        string source,
        DiagnosticAnalyzer analyzer)
    {
        var compilation = CreateCompilation(source);
        var compilationWithAnalyzers = compilation.WithAnalyzers(
            ImmutableArray.Create(analyzer));
        return await compilationWithAnalyzers.GetAnalyzerDiagnosticsAsync();
    }
}
