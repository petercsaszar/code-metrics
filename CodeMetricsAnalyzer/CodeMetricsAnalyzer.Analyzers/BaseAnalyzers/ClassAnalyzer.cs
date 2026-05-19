using System;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers.BaseAnalyzers
{
    public abstract class ClassAnalyzer : BaseCodeMetricsAnalyzer
    {
        public ClassAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override void Initialize(AnalysisContext context)
        {
            context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
            context.EnableConcurrentExecution();
            context.RegisterSyntaxNodeAction(AnalyzeTypeDeclaration,
                SyntaxKind.ClassDeclaration,
                SyntaxKind.StructDeclaration,
                SyntaxKind.RecordDeclaration,
                SyntaxKind.RecordStructDeclaration);
        }

        private void AnalyzeTypeDeclaration(SyntaxNodeAnalysisContext context)
        {
            var typeDecl = (TypeDeclarationSyntax)context.Node;
            var typeSymbol = context.SemanticModel.GetDeclaredSymbol(typeDecl) as INamedTypeSymbol;
            if (typeSymbol == null)
                return;

            // For partial types, only analyse the lexically first declaration so the
            // same diagnostic is not reported once per partial file.
            if (typeSymbol.DeclaringSyntaxReferences.Length > 1)
            {
                var canonical = typeSymbol.DeclaringSyntaxReferences
                    .Select(r => r.GetSyntax())
                    .OfType<TypeDeclarationSyntax>()
                    .OrderBy(d => d.SyntaxTree.FilePath, StringComparer.Ordinal)
                    .ThenBy(d => d.SpanStart)
                    .FirstOrDefault();

                if (!ReferenceEquals(canonical, typeDecl))
                    return;
            }

            AnalyzeClass(context);
        }

        protected abstract void AnalyzeClass(SyntaxNodeAnalysisContext context);
    }
}
