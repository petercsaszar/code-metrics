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
public class LCOM5Analyzer(AnalyzerConfiguration config) : ClassAnalyzer(config)
{
    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => [DiagnosticDescriptors.LCOM5Rule];

    protected override void AnalyzeClass(SyntaxNodeAnalysisContext context)
    {
        var classDeclaration = (ClassDeclarationSyntax)context.Node;
        var semanticModel = context.SemanticModel;
        var classSymbol = semanticModel.GetDeclaredSymbol(classDeclaration);

        if (classSymbol == null)
            return;

        var methods = classSymbol.GetMembers().OfType<IMethodSymbol>()
            .Where(m => m.MethodKind == MethodKind.Ordinary)
            .ToList();

        var fields = classSymbol.GetMembers().OfType<IFieldSymbol>().ToList();

        if (methods.Count < _config.LCOM5Analysis.MinimumMethodCount || fields.Count < _config.LCOM5Analysis.MinimumFieldCount)
            return;

        Dictionary<IMethodSymbol, HashSet<IFieldSymbol>> methodAccesses = new Dictionary<IMethodSymbol, HashSet<IFieldSymbol>>(SymbolEqualityComparer.Default);

        foreach (var method in methods)
        {
            var accessedFields = new HashSet<IFieldSymbol>(SymbolEqualityComparer.Default);

            foreach (var syntaxRef in method.DeclaringSyntaxReferences)
            {
                if (syntaxRef.GetSyntax() is MethodDeclarationSyntax syntax)
                {
                    BlockSyntax? body = syntax.Body; // Normal method body

                    if (body == null && syntax.ExpressionBody != null)
                    {
                        // Handle expression-bodied methods (e.g. int Square(int x) => x * x)
                        body = SyntaxFactory.Block(SyntaxFactory.ExpressionStatement(syntax.ExpressionBody.Expression));
                    }

                    if (body != null)
                    {
                        try
                        {
                            // TODO: Figure out why this is throwing an exception
                            var dataFlow = semanticModel.AnalyzeDataFlow(body);
                            if (dataFlow != null)
                            {
                                foreach (var symbol in dataFlow.ReadInside.Concat(dataFlow.WrittenInside))
                                {
                                    if (symbol is IFieldSymbol fieldSymbol)
                                    {
                                        accessedFields.Add(fieldSymbol);
                                    }
                                }
                            }
                        }
                        catch (ArgumentException)
                        {
                            // Ignore exceptions for now, likely due to generated code
                            //// Debugging prints
                            //Console.WriteLine($"Method: {syntax.Identifier.Text}");
                            //Console.WriteLine($"SyntaxTree: {syntax.SyntaxTree.FilePath}");
                            //Console.WriteLine($"Body SyntaxTree: {body?.SyntaxTree?.FilePath}");
                            //Console.WriteLine($"SemanticModel SyntaxTree: {semanticModel.SyntaxTree.FilePath}");
                        }
                    }
                }
            }

            methodAccesses[method] = accessedFields;
        }

        int k = methods.Count;
        int l = fields.Count;
        double a = 0;

        if (methodAccesses.Count > 0)
        {
            var commonFields = new HashSet<IFieldSymbol>(methodAccesses.Values.First(), SymbolEqualityComparer.Default);

            foreach (var fieldsSet in methodAccesses.Values.Skip(1))
            {
                commonFields.IntersectWith(fieldsSet);
            }

            a = commonFields.Count;
        }

        double LCOM5 = 1 - (a / l);

        //double LCOM5 = (M - (sum_dA / F)) / (M - 1);

        if (LCOM5 > _config.LCOM5Analysis.CohesionThreshold)
        {
            ReportDiagnostics(
                context,
                DiagnosticDescriptors.LCOM5Rule,
                classDeclaration.Identifier.GetLocation(),
                classSymbol.Name, LCOM5);
        }
    }
}