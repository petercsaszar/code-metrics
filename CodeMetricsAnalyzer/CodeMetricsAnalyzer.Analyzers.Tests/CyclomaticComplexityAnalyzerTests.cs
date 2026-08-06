using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

public class CyclomaticComplexityAnalyzerTests
{
    private static CyclomaticComplexityAnalyzer CreateAnalyzer(int threshold = 6) =>
        new(new AnalyzerConfiguration
        {
            CyclomaticComplexityAnalysis = new CyclomaticComplexityAnalysisConfiguration
            {
                MaximumComplexity = threshold
            }
        });

    [Fact]
    public async Task Method_CC1_NoDiagnostic()
    {
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task Method_CC6_AtThreshold_NoDiagnostic()
    {
        // 5 if-statements gives CC = 1+5 = 6, which is NOT > 6 → no diagnostic.
        const string source = """
            class C {
                int M(int a, int b, int c, int d, int e) {
                    if (a > 0) return 1;
                    if (b > 0) return 2;
                    if (c > 0) return 3;
                    if (d > 0) return 4;
                    if (e > 0) return 5;
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task Method_CC7_AboveThreshold_TriggersDiagnostic()
    {
        // 6 if-statements gives CC = 1+6 = 7 > 6 → diagnostic.
        const string source = """
            class C {
                int M(int a, int b, int c, int d, int e, int f) {
                    if (a > 0) return 1;
                    if (b > 0) return 2;
                    if (c > 0) return 3;
                    if (d > 0) return 4;
                    if (e > 0) return 5;
                    if (f > 0) return 6;
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task CustomThreshold_CC3_AtThreshold_NoDiagnostic()
    {
        const string source = """
            class C {
                int M(int a, int b) {
                    if (a > 0) return 1;
                    if (b > 0) return 2;
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 3));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task CustomThreshold_CC4_AboveThreshold_TriggersDiagnostic()
    {
        const string source = """
            class C {
                int M(int a, int b, int c) {
                    if (a > 0) return 1;
                    if (b > 0) return 2;
                    if (c > 0) return 3;
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 3));
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task SwitchDefault_NotCounted_CC4NotCC5()
    {
        // switch with 3 cases + default: CC = 1+3 = 4, default does not add a branch.
        const string source = """
            class C {
                string GetDay(int d) {
                    switch (d) {
                        case 1: return "Mon";
                        case 2: return "Tue";
                        case 3: return "Wed";
                        default: return "Other";
                    }
                }
            }
            """;
        // CC=4 is NOT > 6 → no diagnostic regardless; use threshold=3 to expose if default were counted.
        var diagnosticsAtThreshold3 = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 3));
        Assert.Contains(diagnosticsAtThreshold3, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);

        var diagnosticsAtThreshold4 = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 4));
        Assert.DoesNotContain(diagnosticsAtThreshold4, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task Constructor_HighCC_TriggersDiagnostic()
    {
        const string source = """
            class C {
                private int _v;
                public C(int a, int b, int c, int d, int e, int f) {
                    if (a > 0) _v = a;
                    if (b > 0) _v = b;
                    if (c > 0) _v = c;
                    if (d > 0) _v = d;
                    if (e > 0) _v = e;
                    if (f > 0) _v = f;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
    }

    [Fact]
    public async Task Diagnostic_ContainsMethodName()
    {
        const string source = """
            class C {
                int ComplexMethod(int a, int b, int c, int d, int e, int f) {
                    if (a > 0) return 1;
                    if (b > 0) return 2;
                    if (c > 0) return 3;
                    if (d > 0) return 4;
                    if (e > 0) return 5;
                    if (f > 0) return 6;
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.CyclomaticComplexity);
        Assert.Contains("ComplexMethod", diag.GetMessage());
    }
}
