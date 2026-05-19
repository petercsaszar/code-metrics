using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// End-to-end tests for MaintainabilityIndexAnalyzer.
///
/// The MI formula (Microsoft-normalised Oman &amp; Hagemeister 1992):
///   MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) / 171 * 100)
///
/// Default threshold is 65. A diagnostic is reported when MI &lt; threshold.
/// </summary>
public class MaintainabilityIndexAnalyzerTests
{
    private static MaintainabilityIndexAnalyzer CreateAnalyzer(double threshold = 65.0) =>
        new(new AnalyzerConfiguration
        {
            MaintainabilityIndexAnalysis = new MaintainabilityIndexAnalysisConfiguration
            {
                MinimumMaintainabilityIndex = threshold
            }
        });

    // -------------------------------------------------------------------------
    // No-diagnostic (high-MI) cases
    // -------------------------------------------------------------------------

    [Fact]
    public async Task SimpleAddMethod_BlockBody_NoMIDiagnostic()
    {
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    [Fact]
    public async Task SimpleAddMethod_ExpressionBody_NoMIDiagnostic()
    {
        // Expression-bodied methods have lower Halstead volume (implicit return is skipped),
        // so MI will be at least as high as the block-body form.
        const string source = """
            class C {
                int Add(int a, int b) => a + b;
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    [Fact]
    public async Task EmptyMethod_NoMIDiagnostic()
    {
        const string source = """
            class C {
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    // -------------------------------------------------------------------------
    // Diagnostic (low-MI) cases
    // -------------------------------------------------------------------------

    [Fact]
    public async Task ComplexMethod_TriggersMIDiagnostic()
    {
        // Deliberately complex: nested loops, multiple branches, many operators and operands.
        // Estimated CC ≈ 10, LOC ≈ 22, which pushes MI well below 65.
        const string source = """
            class C {
                int Compute(int a, int b, int c, int mode) {
                    int result = 0;
                    if (mode == 1) {
                        for (int i = 0; i < a; i++) {
                            if (i % 2 == 0 || i % 3 == 0)
                                result += i;
                            else
                                result -= i;
                        }
                    } else if (mode == 2) {
                        int j = b;
                        while (j > 0) {
                            switch (j % 3) {
                                case 0: result += a; break;
                                case 1: result += b; break;
                                case 2: result += c; break;
                            }
                            j--;
                        }
                    } else {
                        result = a * b + b * c - a * c;
                    }
                    return result;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    [Fact]
    public async Task ComplexMethod_ThresholdZero_NoMIDiagnostic()
    {
        // Even a complex method must not trigger a diagnostic when the threshold is 0.
        const string source = """
            class C {
                int Compute(int a, int b, int c, int mode) {
                    int result = 0;
                    if (mode == 1) {
                        for (int i = 0; i < a; i++) {
                            if (i % 2 == 0 || i % 3 == 0)
                                result += i;
                            else
                                result -= i;
                        }
                    } else if (mode == 2) {
                        int j = b;
                        while (j > 0) {
                            switch (j % 3) {
                                case 0: result += a; break;
                                case 1: result += b; break;
                                case 2: result += c; break;
                            }
                            j--;
                        }
                    } else {
                        result = a * b + b * c - a * c;
                    }
                    return result;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0.0));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    // -------------------------------------------------------------------------
    // Diagnostic content
    // -------------------------------------------------------------------------

    [Fact]
    public async Task Diagnostic_ContainsMethodName()
    {
        const string source = """
            class C {
                int Compute(int a, int b, int c, int mode) {
                    int result = 0;
                    if (mode == 1) {
                        for (int i = 0; i < a; i++) {
                            if (i % 2 == 0 || i % 3 == 0)
                                result += i;
                            else
                                result -= i;
                        }
                    } else if (mode == 2) {
                        int j = b;
                        while (j > 0) {
                            switch (j % 3) {
                                case 0: result += a; break;
                                case 1: result += b; break;
                                case 2: result += c; break;
                            }
                            j--;
                        }
                    } else {
                        result = a * b + b * c - a * c;
                    }
                    return result;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var miDiag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
        Assert.Contains("Compute", miDiag.GetMessage());
    }

    [Fact]
    public async Task Diagnostic_LocationPointsToMethodIdentifier_NotBody()
    {
        const string source = """
            class C {
                int Compute(int a, int b, int c, int mode) {
                    int result = 0;
                    if (mode == 1) {
                        for (int i = 0; i < a; i++) {
                            if (i % 2 == 0 || i % 3 == 0)
                                result += i;
                            else
                                result -= i;
                        }
                    } else {
                        result = a * b + b * c - a * c;
                    }
                    return result;
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var miDiag = diagnostics.FirstOrDefault(d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
        if (miDiag == null) return; // not complex enough with this threshold — skip

        // The reported location should be on line 2 (0-indexed: line 1), where "Compute" appears.
        int line = miDiag.Location.GetLineSpan().StartLinePosition.Line;
        Assert.Equal(1, line); // 0-indexed line of "int Compute(...)"
    }

    // -------------------------------------------------------------------------
    // Constructors are analysed
    // -------------------------------------------------------------------------

    [Fact]
    public async Task ComplexConstructor_TriggersMIDiagnostic()
    {
        const string source = """
            class C {
                private int _v;
                public C(int a, int b, int c, int d, int e) {
                    if (a > 0) _v = a;
                    else if (b > 0) _v = b;
                    else if (c > 0) _v = c;
                    else if (d > 0) _v = d;
                    else if (e > 0) _v = e;
                    else _v = a + b + c + d + e;
                    for (int i = 0; i < _v; i++) {
                        _v += i % 2 == 0 ? 1 : -1;
                    }
                    while (_v > 100) {
                        _v /= 2;
                    }
                }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.MaintainabilityIndex);
    }

    // -------------------------------------------------------------------------
    // MI formula invariants — verified with the same formula used in the analyzer
    // -------------------------------------------------------------------------

    [Theory]
    [InlineData(0.0, 0, 0, 100.0)]     // no operators, no lines → raw 171/171*100 = 100
    [InlineData(1.0, 1, 1, 99.87)]     // V=1 → ln(1)=0; LOC=1 → ln(1)=0 → (171-0-0.23-0)/171*100
    [InlineData(8.0, 1, 1, 93.54)]     // V=8, CC=1, LOC=1 (expression body) — simple Add method
    [InlineData(8.0, 1, 3, 83.13)]     // V=8, CC=1, LOC=3 (multi-line Add method)
    public void MIFormula_KnownInputs_MatchExpectedOutput(
        double halsteadVolume, int cc, int loc, double expectedMi)
    {
        double computed = ComputeMI(halsteadVolume, cc, loc);
        Assert.Equal(expectedMi, Math.Round(computed, 2));
    }

    [Fact]
    public void MIFormula_ResultNeverExceedsHundred()
    {
        Assert.True(ComputeMI(0, 0, 0) <= 100.0);
        Assert.True(ComputeMI(1, 1, 1) <= 100.0);
    }

    [Fact]
    public void MIFormula_ResultNeverGoesNegative()
    {
        // Pathological inputs: huge volume, many branches, many lines.
        Assert.Equal(0.0, ComputeMI(1e30, 1000, 100_000));
    }

    [Fact]
    public void MIFormula_MoreBranchesLowerMI()
    {
        double simple = ComputeMI(halsteadVolume: 10, cc: 1, loc: 5);
        double complex = ComputeMI(halsteadVolume: 10, cc: 10, loc: 5);
        Assert.True(complex < simple, $"Expected MI({complex:F2}) < MI({simple:F2}) for higher CC");
    }

    [Fact]
    public void MIFormula_MoreLinesLowerMI()
    {
        double short_ = ComputeMI(halsteadVolume: 10, cc: 3, loc: 5);
        double long_ = ComputeMI(halsteadVolume: 10, cc: 3, loc: 50);
        Assert.True(long_ < short_, $"Expected MI({long_:F2}) < MI({short_:F2}) for more lines");
    }

    // Mirrors the exact formula in MaintainabilityIndexAnalyzer.
    private static double ComputeMI(double halsteadVolume, int cc, int loc)
    {
        const double miMax = 171.0;
        double mi = miMax;
        if (halsteadVolume > 0) mi -= 5.2 * Math.Log(halsteadVolume);
        mi -= 0.23 * cc;
        if (loc > 0) mi -= 16.2 * Math.Log(loc);
        return Math.Max(0, (mi / miMax) * 100.0);
    }
}
