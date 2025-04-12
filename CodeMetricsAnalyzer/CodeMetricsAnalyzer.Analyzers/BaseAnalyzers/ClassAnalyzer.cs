using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis.CSharp;
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
            context.RegisterSyntaxNodeAction(AnalyzeClass, SyntaxKind.ClassDeclaration);
        }

        protected abstract void AnalyzeClass(SyntaxNodeAnalysisContext context);
    }
}
