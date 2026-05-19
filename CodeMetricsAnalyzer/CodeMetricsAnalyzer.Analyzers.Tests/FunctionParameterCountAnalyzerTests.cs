using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

public class FunctionParameterCountAnalyzerTests
{
    private static FunctionParameterCountAnalyzer CreateAnalyzer(int threshold = 2) =>
        new(new AnalyzerConfiguration
        {
            FunctionParameterCountAnalysis = new FunctionParameterCountAnalysisConfiguration
            {
                ParameterCountThreshold = threshold
            }
        });

    [Fact]
    public async Task ZeroParams_NoDiagnostic()
    {
        const string source = """
            class C {
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task TwoParams_AtThreshold_NoDiagnostic()
    {
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task ThreeParams_AboveThreshold_TriggersDiagnostic()
    {
        const string source = """
            class C {
                int Add(int a, int b, int c) { return a + b + c; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task ExtensionMethod_ThisParamExcluded_NoDiagnostic()
    {
        // 'this' parameter must not count toward the limit.
        // Extension method has 3 parameters syntactically but only 2 are real.
        const string source = """
            static class Extensions {
                public static int Add(this int a, int b, int c) => a + b + c;
            }
            """;
        // threshold=2: real params = b, c → count = 2, NOT > 2 → no diagnostic
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task Constructor_ThreeParams_TriggersDiagnostic()
    {
        const string source = """
            class C {
                private int _a, _b, _c;
                public C(int a, int b, int c) { _a = a; _b = b; _c = c; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task PropertyAccessor_NoDiagnostic()
    {
        // Accessors have no parameter list and must be skipped entirely.
        const string source = """
            class C {
                private int _x;
                public int X {
                    get { return _x; }
                    set { _x = value; }
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
    }

    [Fact]
    public async Task Diagnostic_ContainsMethodNameAndCounts()
    {
        const string source = """
            class C {
                int Compute(int a, int b, int c) { return a + b + c; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.FunctionParameterCount);
        var message = diag.GetMessage();
        Assert.Contains("Compute", message);
        Assert.Contains("3", message); // actual count
        Assert.Contains("2", message); // threshold
    }
}
