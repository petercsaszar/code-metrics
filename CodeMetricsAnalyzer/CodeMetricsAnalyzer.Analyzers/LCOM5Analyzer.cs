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
            var typeDeclaration = (TypeDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;
            var typeSymbol = semanticModel.GetDeclaredSymbol(typeDeclaration) as INamedTypeSymbol;

            if (typeSymbol == null)
                return;

            // Only non-static ordinary methods are meaningful for LCOM.
            var methods = typeSymbol.GetMembers().OfType<IMethodSymbol>()
                .Where(m => m.MethodKind == MethodKind.Ordinary && !m.IsStatic)
                .ToList();

            // l = number of tracked instance attributes (non-static explicit fields + properties).
            // Backing fields of auto-properties are excluded to avoid double-counting.
            int l = MetricsHelper.GetTrackedMemberCount(typeSymbol);
            int k = methods.Count;

            if (k < _config.LCOM5Analysis.MinimumMethodCount || l < _config.LCOM5Analysis.MinimumMemberCount)
                return;

            // k == 1 makes the denominator zero — formula is undefined for single-method classes.
            if (k == 1)
                return;

            var methodAccesses = new Dictionary<IMethodSymbol, HashSet<ISymbol>>(SymbolEqualityComparer.Default);

            foreach (var method in methods)
            {
                var accessedMembers = new HashSet<ISymbol>(SymbolEqualityComparer.Default);

                foreach (var syntaxRef in method.DeclaringSyntaxReferences)
                {
                    if (!(syntaxRef.GetSyntax() is MethodDeclarationSyntax syntax))
                        continue;

                    var methodSemanticModel = semanticModel.Compilation.GetSemanticModel(syntax.SyntaxTree);

                    // Use operation-based analysis so that auto-property accesses are counted.
                    Microsoft.CodeAnalysis.IOperation rootOp = null;
                    if (syntax.Body != null)
                        rootOp = methodSemanticModel.GetOperation(syntax.Body);
                    else if (syntax.ExpressionBody?.Expression != null)
                        rootOp = methodSemanticModel.GetOperation(syntax.ExpressionBody.Expression);

                    if (rootOp != null)
                        MetricsHelper.CollectMemberAccesses(rootOp, accessedMembers, typeSymbol);
                }

                methodAccesses[method] = accessedMembers;
            }

            // a = total member-method access pairs (sum of distinct members accessed per method).
            double a = methodAccesses.Values.Sum(members => members.Count);

            // Henderson-Sellers (1996): LCOM5 = (a̅ - k) / (1 - k)
            // where a̅ = a/l (mean number of methods accessing each attribute).
            // Rewritten to avoid a separate division: (a - k*l) / (l - k*l).
            // Denominator is always negative for k > 1, l >= 1, so result is in [0, k/(k-1)].
            double denominator = l - ((double)k * l);
            double lcom5 = (a - ((double)k * l)) / denominator;

            if (lcom5 > _config.LCOM5Analysis.CohesionThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.LCOM5Rule,
                    typeDeclaration.Identifier.GetLocation(),
                    typeSymbol.Name,
                    lcom5);
            }
        }
    }
}
