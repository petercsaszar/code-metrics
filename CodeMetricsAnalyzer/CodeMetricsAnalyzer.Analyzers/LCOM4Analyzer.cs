using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers;

[DiagnosticAnalyzer(LanguageNames.CSharp)]
public class LCOM4Analyzer(AnalyzerConfiguration config) : ClassAnalyzer(config)
{
    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => [DiagnosticDescriptors.LCOM4Rule];

    protected override void AnalyzeClass(SyntaxNodeAnalysisContext context)
    {
        var classDecl = (ClassDeclarationSyntax)context.Node;
        var semanticModel = context.SemanticModel;
        var classSymbol = semanticModel.GetDeclaredSymbol(classDecl);

        if (classSymbol == null) return;

        var methods = classSymbol.GetMembers().OfType<IMethodSymbol>()
            .Where(m => m.MethodKind == MethodKind.Ordinary && !m.IsStatic)
            .ToList();

        var fields = classSymbol.GetMembers().OfType<IFieldSymbol>().ToList();

        if (methods.Count < _config.LCOM4Analysis.MinimumMethodCount || fields.Count < _config.LCOM4Analysis.MinimumFieldCount)
            return;

        var methodGraph = new Dictionary<IMethodSymbol, HashSet<IMethodSymbol>>(SymbolEqualityComparer.Default);
        var fieldAccessMap = new Dictionary<IMethodSymbol, HashSet<IFieldSymbol>>(SymbolEqualityComparer.Default);

        foreach (var method in methods)
        {
            var connected = new HashSet<IMethodSymbol>(SymbolEqualityComparer.Default);
            var accessedFields = new HashSet<IFieldSymbol>(SymbolEqualityComparer.Default);

            foreach (var syntaxRef in method.DeclaringSyntaxReferences)
            {
                var methodNode = syntaxRef.GetSyntax() as MethodDeclarationSyntax;
                if (methodNode?.Body == null && methodNode?.ExpressionBody == null) continue;

                var body = methodNode.Body ??
                           SyntaxFactory.Block(SyntaxFactory.ExpressionStatement(methodNode.ExpressionBody!.Expression));

                SyntaxNode? analysisTarget = methodNode.Body ?? (SyntaxNode?)methodNode.ExpressionBody?.Expression;

                if (analysisTarget == null || !semanticModel.SyntaxTree.Equals(analysisTarget.SyntaxTree))
                    continue;

                var dataFlow = semanticModel.AnalyzeDataFlow(analysisTarget);

                foreach (var symbol in dataFlow.ReadInside.Concat(dataFlow.WrittenInside))
                {
                    if (symbol is IFieldSymbol fieldSymbol)
                        accessedFields.Add(fieldSymbol);
                }

                var invocations = methodNode.DescendantNodes().OfType<InvocationExpressionSyntax>();
                foreach (var invocation in invocations)
                {
                    var called = semanticModel.GetSymbolInfo(invocation).Symbol as IMethodSymbol;
                    if (called != null && methods.Contains(called) && !SymbolEqualityComparer.Default.Equals(called, method))
                    {
                        connected.Add(called);
                    }
                }
            }

            fieldAccessMap[method] = accessedFields;
            methodGraph[method] = connected;
        }

        // Add connections via shared field access
        foreach (var m1 in methods)
        {
            foreach (var m2 in methods)
            {
                if (SymbolEqualityComparer.Default.Equals(m1, m2)) continue;

                if (fieldAccessMap[m1].Overlaps(fieldAccessMap[m2]))
                {
                    methodGraph[m1].Add(m2);
                    methodGraph[m2].Add(m1);
                }
            }
        }

        // Count connected components
        var visited = new HashSet<IMethodSymbol>(SymbolEqualityComparer.Default);
        int components = 0;

        void DFS(IMethodSymbol node)
        {
            if (!visited.Add(node)) return;
            foreach (var neighbor in methodGraph[node])
            {
                DFS(neighbor);
            }
        }

        foreach (var method in methods)
        {
            if (!visited.Contains(method))
            {
                components++;
                DFS(method);
            }
        }

        if (components > _config.LCOM4Analysis.CohesionThreshold)
        {
            ReportDiagnostics(
                context,
                DiagnosticDescriptors.LCOM4Rule,
                classDecl.Identifier.GetLocation(),
                classSymbol.Name,
                components);
        }
    }
}