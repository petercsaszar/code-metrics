using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class LCOM4Analyzer : ClassAnalyzer
    {
        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.LCOM4Rule);

        public LCOM4Analyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        protected override void AnalyzeClass(SyntaxNodeAnalysisContext context)
        {
            var typeDecl = (TypeDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;

            var typeSymbol = semanticModel.GetDeclaredSymbol(typeDecl) as INamedTypeSymbol;
            if (typeSymbol == null)
                return;

            // Only non-static ordinary methods are meaningful for LCOM.
            var methods = typeSymbol.GetMembers().OfType<IMethodSymbol>()
                .Where(m => m.MethodKind == MethodKind.Ordinary && !m.IsStatic)
                .ToList();

            int memberCount = MetricsHelper.GetTrackedMemberCount(typeSymbol);

            if (methods.Count < _config.LCOM4Analysis.MinimumMethodCount ||
                memberCount < _config.LCOM4Analysis.MinimumMemberCount)
                return;

            // O(1) membership test for called-method detection (fixes O(n) per invocation).
            var methodSet = new HashSet<IMethodSymbol>(methods, SymbolEqualityComparer.Default);

            var methodGraph = new Dictionary<IMethodSymbol, HashSet<IMethodSymbol>>(SymbolEqualityComparer.Default);
            var memberAccessMap = new Dictionary<IMethodSymbol, HashSet<ISymbol>>(SymbolEqualityComparer.Default);

            foreach (var method in methods)
            {
                var connectedByCall = new HashSet<IMethodSymbol>(SymbolEqualityComparer.Default);
                var accessedMembers = new HashSet<ISymbol>(SymbolEqualityComparer.Default);

                foreach (var syntaxRef in method.DeclaringSyntaxReferences)
                {
                    if (!(syntaxRef.GetSyntax() is MethodDeclarationSyntax methodNode))
                        continue;

                    // Use the tree-specific semantic model so cross-file partial classes work.
                    var methodSemanticModel = semanticModel.Compilation.GetSemanticModel(methodNode.SyntaxTree);

                    // Collect field + property accesses via operation analysis so that
                    // auto-property access (this.Prop = x) is counted, not just raw field writes.
                    Microsoft.CodeAnalysis.IOperation rootOp = null;
                    if (methodNode.Body != null)
                        rootOp = methodSemanticModel.GetOperation(methodNode.Body);
                    else if (methodNode.ExpressionBody?.Expression != null)
                        rootOp = methodSemanticModel.GetOperation(methodNode.ExpressionBody.Expression);

                    if (rootOp != null)
                        MetricsHelper.CollectMemberAccesses(rootOp, accessedMembers, typeSymbol);

                    // Connect methods that call each other directly.
                    foreach (var invocation in methodNode.DescendantNodes().OfType<InvocationExpressionSyntax>())
                    {
                        var called = methodSemanticModel.GetSymbolInfo(invocation).Symbol as IMethodSymbol;
                        if (called != null &&
                            methodSet.Contains(called) &&
                            !SymbolEqualityComparer.Default.Equals(called, method))
                        {
                            connectedByCall.Add(called);
                        }
                    }
                }

                memberAccessMap[method] = accessedMembers;
                methodGraph[method] = connectedByCall;
            }

            // Connect methods that share at least one accessed member.
            for (int i = 0; i < methods.Count; i++)
            {
                for (int j = i + 1; j < methods.Count; j++)
                {
                    if (memberAccessMap[methods[i]].Overlaps(memberAccessMap[methods[j]]))
                    {
                        methodGraph[methods[i]].Add(methods[j]);
                        methodGraph[methods[j]].Add(methods[i]);
                    }
                }
            }

            // Count connected components via DFS.
            var visited = new HashSet<IMethodSymbol>(SymbolEqualityComparer.Default);
            int components = 0;

            foreach (var method in methods)
            {
                if (visited.Contains(method))
                    continue;

                components++;
                var stack = new Stack<IMethodSymbol>();
                stack.Push(method);

                while (stack.Count > 0)
                {
                    var node = stack.Pop();
                    if (!visited.Add(node))
                        continue;

                    foreach (var neighbor in methodGraph[node])
                        stack.Push(neighbor);
                }
            }

            if (components > _config.LCOM4Analysis.CohesionThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.LCOM4Rule,
                    typeDecl.Identifier.GetLocation(),
                    typeSymbol.Name,
                    components);
            }
        }
    }
}
