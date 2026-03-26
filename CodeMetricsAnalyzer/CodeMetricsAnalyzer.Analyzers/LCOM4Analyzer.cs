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
            var classDecl = (ClassDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;


            var classSymbol = semanticModel.GetDeclaredSymbol(classDecl) as INamedTypeSymbol;
            if (classSymbol == null)
                return;

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
                    if (!(syntaxRef.GetSyntax() is MethodDeclarationSyntax methodNode))
                        continue;

                    if (methodNode.Body == null && methodNode.ExpressionBody == null)
                        continue;

                    if (methodNode.Body != null)
                    {
                        var dataFlow = semanticModel.AnalyzeDataFlow(methodNode.Body);
                        if (dataFlow != null)
                            CollectFieldAccesses(dataFlow, accessedFields);
                    }
                    else if (methodNode.ExpressionBody != null)
                    {
                        var dataFlow = semanticModel.AnalyzeDataFlow(
                            methodNode.ExpressionBody.Expression,
                            methodNode.ExpressionBody.Expression);
                        if (dataFlow != null)
                            CollectFieldAccesses(dataFlow, accessedFields);
                    }

                    var invocations = methodNode.DescendantNodes().OfType<InvocationExpressionSyntax>();
                    foreach (var invocation in invocations)
                    {
                        var called = semanticModel.GetSymbolInfo(invocation).Symbol as IMethodSymbol;


                        if (called != null
                            && methods.Any(m => SymbolEqualityComparer.Default.Equals(m, called))
                            && !SymbolEqualityComparer.Default.Equals(called, method))
                        {
                            connected.Add(called);
                        }
                    }
                }

                fieldAccessMap[method] = accessedFields;
                methodGraph[method] = connected;
            }

            for (int i = 0; i < methods.Count; i++)
            {
                for (int j = i + 1; j < methods.Count; j++)
                {
                    if (fieldAccessMap[methods[i]].Overlaps(fieldAccessMap[methods[j]]))
                    {
                        methodGraph[methods[i]].Add(methods[j]);
                        methodGraph[methods[j]].Add(methods[i]);
                    }
                }
            }

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
                    classDecl.Identifier.GetLocation(),
                    classSymbol.Name,
                    components);
            }
        }

        private static void CollectFieldAccesses(
            Microsoft.CodeAnalysis.DataFlowAnalysis dataFlow,
            HashSet<IFieldSymbol> accessedFields)
        {
            foreach (var symbol in dataFlow.ReadInside.Concat(dataFlow.WrittenInside))
            {
                if (symbol is IFieldSymbol fieldSymbol)
                    accessedFields.Add(fieldSymbol);
            }
        }
    }
}