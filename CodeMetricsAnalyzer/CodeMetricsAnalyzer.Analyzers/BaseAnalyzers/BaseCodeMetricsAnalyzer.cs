using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers.BaseAnalyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public abstract class BaseCodeMetricsAnalyzer : DiagnosticAnalyzer
    {
        protected readonly AnalyzerConfiguration _config;

        public BaseCodeMetricsAnalyzer(AnalyzerConfiguration config)
        {
            _config = config;
        }

        public virtual void ReportDiagnostics(SyntaxNodeAnalysisContext context)
        {

        }

        protected static void ReportDiagnostics(SyntaxNodeAnalysisContext context, DiagnosticDescriptor descriptor, Location? location, params object?[]? messageArgs)
        {
            if (location is null || location == Location.None)
            {
                var diagnosticWithoutLocation = Diagnostic.Create(descriptor, location, messageArgs);
                context.ReportDiagnostic(diagnosticWithoutLocation);
                return;
            }

            var syntaxTree = context.Compilation.SyntaxTrees.FirstOrDefault(syntaxTree => syntaxTree.FilePath == location!.SourceTree?.FilePath);
            if (syntaxTree is null)
            {
                return;
            }

            var newLocation = Location.Create(syntaxTree, location!.SourceSpan);
            var diagnostic = Diagnostic.Create(descriptor, newLocation, messageArgs);

            context.ReportDiagnostic(diagnostic);
        }
    }
}
