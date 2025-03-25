using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

[DiagnosticAnalyzer(LanguageNames.CSharp)]
public class LCOM5Analyzer : DiagnosticAnalyzer
{
    private readonly AnalyzerConfiguration _config;

    public LCOM5Analyzer(AnalyzerConfiguration config)
    {
        _config = config;
    }

    private static readonly DiagnosticDescriptor Rule = new DiagnosticDescriptor(
        "LCOM5",
        "Lack of Cohesion of Methods (LCOM5)",
        "Class '{0}' has an LCOM5 value of {1}. Consider refactoring.",
        "Cohesion",
        DiagnosticSeverity.Warning,
        isEnabledByDefault: true);

    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => ImmutableArray.Create(Rule);

    public override void Initialize(AnalysisContext context)
    {
        context.RegisterSyntaxNodeAction(AnalyzeClass, SyntaxKind.ClassDeclaration);
    }

    private void AnalyzeClass(SyntaxNodeAnalysisContext context)
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

        if (methods.Count < 2 || fields.Count == 0)
            return;

        Dictionary<IMethodSymbol, HashSet<IFieldSymbol>> methodAccesses = new();

        foreach (var method in methods)
        {
            var accessedFields = new HashSet<IFieldSymbol>();

            foreach (var syntaxRef in method.DeclaringSyntaxReferences)
            {
                var syntax = syntaxRef.GetSyntax() as MethodDeclarationSyntax;
                if (syntax != null)
                {
                    BlockSyntax? body = syntax.Body; // Normal method body

                    if (body == null && syntax.ExpressionBody != null)
                    {
                        // Handle expression-bodied methods (e.g., `int Square(int x) => x * x;`)
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
                        catch (Exception)
                        {
                            // Ignore exceptions for now
                            // Debugging prints
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

        int M = methods.Count;
        int V = fields.Count;
        double sum_Ai = methodAccesses.Values.Sum(set => set.Count);

        double LCOM5 = (M - (sum_Ai / V)) / (M - 1);

        if (LCOM5 > _config.LCOM5Analysis.LCOM5CohesionThreshold) // Alert if cohesion is low
        {
            var diagnostic = Diagnostic.Create(Rule, classDeclaration.Identifier.GetLocation(), classSymbol.Name, LCOM5);
            context.ReportDiagnostic(diagnostic);
        }
    }
}
