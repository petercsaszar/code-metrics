using System.Collections.Immutable;
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

        protected static void ReportDiagnostics(
            SyntaxNodeAnalysisContext context,
            DiagnosticDescriptor descriptor,
            Location location,
            params object[] messageArgs)
        {
            var diagnostic = Diagnostic.Create(descriptor, location, messageArgs);
            context.ReportDiagnostic(diagnostic);
        }
    }
}
