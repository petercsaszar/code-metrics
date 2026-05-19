using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// Tests for BumpyRoadAnalyzer.
///
/// A "bump" is a code region where logic is nested at least 2 levels deep.
/// The score formula (0–10 scale, reference worst-case ≈ 189 raw units):
///   bumpArea per bump = sum of (max depth per line − 1) for lines in bump
///   total = sum(bumpArea) × (1 + ln(bumpCount))
///   score = min(10, total / 189 × 10)
///
/// Default threshold is 2.0.
/// </summary>
public class BumpyRoadAnalyzerTests
{
    private static BumpyRoadAnalyzer CreateAnalyzer(int threshold = 2) =>
        new(new AnalyzerConfiguration
        {
            BumpyRoadAnalysis = new BumpyRoadAnalysisConfiguration
            {
                BumpynessThreshold = threshold
            }
        });

    [Fact]
    public async Task FlatMethod_NoBumps_NoDiagnostic()
    {
        const string source = """
            class C {
                int M(int x, int y) {
                    int sum = x + y;
                    int diff = x - y;
                    return sum * diff;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task SingleLevelNesting_DepthOnlyOne_NoDiagnostic()
    {
        // The bump threshold is depth >= 2. A single if at the top level is depth 1 — no bump.
        const string source = """
            class C {
                int M(int x, int y) {
                    if (x > y) return x;
                    return y;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task SmallNestedBlock_LowScore_NoDiagnostic()
    {
        // One 2-line bump at depth 2 produces a score ≈ 0.1, well below threshold 2.
        const string source = """
            class C {
                int M(int x, int y) {
                    if (x > 0) {
                        if (y > 0)
                            return x + y;
                    }
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task ThreeLargeBumpRegions_HighScore_TriggersDiagnostic()
    {
        // 3 separate bump regions each with 10 lines at depth 2.
        // Estimated score: (30 × (1 + ln3)) / 189 × 10 ≈ 3.3 > threshold 2.
        const string source = """
            class C {
                void Complex(int a, int b, int c, bool p, bool q, bool r) {
                    if (p) {
                        if (a > 0) {
                            int v1 = a + b;
                            int v2 = b + c;
                            int v3 = v1 * v2;
                            int v4 = a - b;
                            int v5 = b - c;
                            int v6 = v4 + v5;
                            int v7 = v3 - v6;
                            int v8 = v7 + a;
                            int v9 = v8 * b;
                        }
                    }
                    if (q) {
                        if (b > 0) {
                            int w1 = a * b;
                            int w2 = b * c;
                            int w3 = w1 + w2;
                            int w4 = a * c;
                            int w5 = w3 - w4;
                            int w6 = w5 + b;
                            int w7 = w6 * a;
                            int w8 = w7 + c;
                            int w9 = w8 - b;
                        }
                    }
                    if (r) {
                        if (c > 0) {
                            int u1 = a + c;
                            int u2 = c - b;
                            int u3 = u1 * u2;
                            int u4 = a - c;
                            int u5 = u3 + u4;
                            int u6 = u5 - a;
                            int u7 = u6 * c;
                            int u8 = u7 + b;
                            int u9 = u8 * a;
                        }
                    }
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task ExpressionBodyMethod_AlwaysSkipped_NoDiagnostic()
    {
        // Expression-bodied members are always skipped (no block body, no nesting possible).
        const string source = """
            class C {
                int Add(int a, int b) => a + b;
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task LowThreshold_TinyBump_TriggersDiagnostic()
    {
        // With threshold = 0 (score must be > 0) any non-empty bump triggers the diagnostic.
        const string source = """
            class C {
                int M(int x, int y) {
                    if (x > 0) {
                        if (y > 0)
                            return x + y;
                    }
                    return 0;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0));
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.BumpyRoad);
    }

    [Fact]
    public async Task Diagnostic_ContainsMethodName()
    {
        // Same structure as ThreeLargeBumpRegions — one statement per line to maximise bumpArea.
        const string source = """
            class C {
                void BumpyMethod(int a, int b, int c, bool p, bool q, bool r) {
                    if (p) {
                        if (a > 0) {
                            int v1 = a + b;
                            int v2 = b + c;
                            int v3 = v1 * v2;
                            int v4 = a - b;
                            int v5 = b - c;
                            int v6 = v4 + v5;
                            int v7 = v3 - v6;
                            int v8 = v7 + a;
                            int v9 = v8 * b;
                        }
                    }
                    if (q) {
                        if (b > 0) {
                            int w1 = a * b;
                            int w2 = b * c;
                            int w3 = w1 + w2;
                            int w4 = a * c;
                            int w5 = w3 - w4;
                            int w6 = w5 + b;
                            int w7 = w6 * a;
                            int w8 = w7 + c;
                            int w9 = w8 - b;
                        }
                    }
                    if (r) {
                        if (c > 0) {
                            int u1 = a + c;
                            int u2 = c - b;
                            int u3 = u1 * u2;
                            int u4 = a - c;
                            int u5 = u3 + u4;
                            int u6 = u5 - a;
                            int u7 = u6 * c;
                            int u8 = u7 + b;
                            int u9 = u8 * a;
                        }
                    }
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.FirstOrDefault(d => d.Id == DiagnosticIdentifiers.BumpyRoad);
        Assert.NotNull(diag);
        Assert.Contains("BumpyMethod", diag.GetMessage());
    }
}
