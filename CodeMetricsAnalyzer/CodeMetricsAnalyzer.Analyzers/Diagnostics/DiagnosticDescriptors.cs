using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.CodeAnalysis;

namespace CodeMetricsAnalyzer.Analyzers.Diagnostics
{
    public static class DiagnosticDescriptors
    {
        public static readonly DiagnosticDescriptor BumpyRoadRule = new DiagnosticDescriptor(
            id: DiagnosticIdentifiers.BumpyRoad,
            title: "Bumpy Road Code Smell",
            messageFormat: "Method '{0}' has a high bumpy road score ({1:F2})",
            category: "CodeMetrics",
            defaultSeverity: DiagnosticSeverity.Warning,
            isEnabledByDefault: true,
            description: "This method has a high level of statement nesting, making it harder to read. Consider refactoring deeply nested structures."
        );

        public static readonly DiagnosticDescriptor FunctionParameterCountRule = new DiagnosticDescriptor(
            id: DiagnosticIdentifiers.FunctionParameterCount,
            title: "Method has too many parameters",
            messageFormat: "Method '{0}' has {1} parameters, which exceeds the defined threshold of {2}",
            category: "CodeMetrics",
            defaultSeverity: DiagnosticSeverity.Warning,
            isEnabledByDefault: true,
            description: "This method has too many parameters, making it harder to understand and maintain."
        );

        public static readonly DiagnosticDescriptor LCOM4Rule = new DiagnosticDescriptor(
            id: DiagnosticIdentifiers.LCOM4,
            title: "Lack of Cohesion of Methods (LCOM4)",
            messageFormat: "Class '{0}' has a high LCOM4 score ({1:F2})",
            category: "CodeMetrics",
            defaultSeverity: DiagnosticSeverity.Warning,
            isEnabledByDefault: true,
            description: "This class has a high LCOM4 score, indicating low cohesion. Consider refactoring."
        );

        public static readonly DiagnosticDescriptor LCOM5Rule = new DiagnosticDescriptor(
            id: DiagnosticIdentifiers.LCOM5,
            title: "Lack of Cohesion of Methods (LCOM5)",
            messageFormat: "Class '{0}' has a high LCOM5 score ({1:F2})",
            category: "CodeMetrics",
            defaultSeverity: DiagnosticSeverity.Warning,
            isEnabledByDefault: true,
            description: "This class has a high LCOM5 score, indicating low cohesion. Consider refactoring."
        );
    }
}
