using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using CodeMetricsAnalyzer.Analyzers.Configurations;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class FunctionParamterCountAnalyzer : DiagnosticAnalyzer
    {
        private readonly AnalyzerConfiguration _config;

        public FunctionParamterCountAnalyzer(AnalyzerConfiguration config)
        {
            _config = config;
        }

        private const string DiagnosticId = "FPC001";
        private const string Title = "Too many parameters";
        private const string MessageFormat = "Method '{0}' has {1} parameters, which exceeds the defined threshold of {2}.";
        private const string Category = "CodeQuality";

        private static readonly DiagnosticDescriptor Rule = new DiagnosticDescriptor(
            DiagnosticId, Title, MessageFormat, Category,
            DiagnosticSeverity.Warning, isEnabledByDefault: true);

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => ImmutableArray.Create(Rule);

        public override void Initialize(AnalysisContext context)
        {
            context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
            context.EnableConcurrentExecution();
            context.RegisterSyntaxNodeAction(AnalyzeMethod, SyntaxKind.MethodDeclaration);
        }

        private void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;
            int parameterCount = methodDeclaration.ParameterList.Parameters.Count;

            if (parameterCount > _config.FunctionParameterCountAnalysis.ParameterCountThreshold)
            {
                var diagnostic = Diagnostic.Create(
                    Rule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    parameterCount,
                    _config.FunctionParameterCountAnalysis.ParameterCountThreshold);

                context.ReportDiagnostic(diagnostic);
            }
        }
    }
}
