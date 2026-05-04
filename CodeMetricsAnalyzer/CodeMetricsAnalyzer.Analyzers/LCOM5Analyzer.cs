using System;
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
    public class LCOM5Analyzer : ClassAnalyzer
    {
        public LCOM5Analyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.LCOM5Rule);

        protected override void AnalyzeClass(SyntaxNodeAnalysisContext context)
        {
            var classDeclaration = (ClassDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;
            var classSymbol = semanticModel.GetDeclaredSymbol(classDeclaration) as INamedTypeSymbol;

            if (classSymbol == null)
                return;

            var methods = classSymbol.GetMembers().OfType<IMethodSymbol>()
                .Where(m => m.MethodKind == MethodKind.Ordinary)
                .ToList();

            var fields = classSymbol.GetMembers().OfType<IFieldSymbol>().ToList();

            int k = methods.Count;
            int l = fields.Count;

            if (k < _config.LCOM5Analysis.MinimumMethodCount || l < _config.LCOM5Analysis.MinimumFieldCount)
                return;

            if (k == 1)
                return;

            var methodAccesses = new Dictionary<IMethodSymbol, HashSet<IFieldSymbol>>(SymbolEqualityComparer.Default);

            foreach (var method in methods)
            {
                var accessedFields = new HashSet<IFieldSymbol>(SymbolEqualityComparer.Default);

                foreach (var syntaxRef in method.DeclaringSyntaxReferences)
                {
                    if (!(syntaxRef.GetSyntax() is MethodDeclarationSyntax syntax))
                        continue;

                    var methodSemanticModel = semanticModel.Compilation.GetSemanticModel(syntax.SyntaxTree);

                    if (syntax.Body != null)
                    {
                        var dataFlow = methodSemanticModel.AnalyzeDataFlow(syntax.Body);
                        if (dataFlow != null)
                            CollectFieldAccesses(dataFlow, accessedFields);
                    }
                    else if (syntax.ExpressionBody != null)
                    {
                        var dataFlow = methodSemanticModel.AnalyzeDataFlow(
                            syntax.ExpressionBody.Expression,
                            syntax.ExpressionBody.Expression);
                        if (dataFlow != null)
                            CollectFieldAccesses(dataFlow, accessedFields);
                    }
                }

                methodAccesses[method] = accessedFields;
            }

            double a = methodAccesses.Values.Sum(accessedFields => accessedFields.Count);

            // LCOM5 = (a - k*l) / (l - k*l)   [Henderson-Sellers 1996]
            double denominator = l - ((double)k * l);

            double lcom5 = (a - ((double)k * l)) / denominator;

            if (lcom5 > _config.LCOM5Analysis.CohesionThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.LCOM5Rule,
                    classDeclaration.Identifier.GetLocation(),
                    classSymbol.Name,
                    lcom5);
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