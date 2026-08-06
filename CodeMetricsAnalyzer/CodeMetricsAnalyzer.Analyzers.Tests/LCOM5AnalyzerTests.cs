using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// Tests for LCOM5Analyzer.
///
/// Henderson-Sellers (1996) formula: LCOM5 = (a − k·l) / (l − k·l)
///   a = sum of distinct members accessed per method
///   k = number of non-static ordinary methods
///   l = number of tracked instance members (explicit fields + non-indexer properties;
///       auto-property backing fields excluded to avoid double-counting)
///
/// Default threshold is 0.5; diagnostic when LCOM5 > 0.5.
/// Minimum: 2 methods, 1 member; k=1 makes the denominator zero (skipped).
/// </summary>
public class LCOM5AnalyzerTests
{
    private static LCOM5Analyzer CreateAnalyzer(double threshold = 0.5, int minMethods = 2, int minMembers = 1) =>
        new(new AnalyzerConfiguration
        {
            LCOM5Analysis = new LCOM5AnalysisConfiguration
            {
                CohesionThreshold = threshold,
                MinimumMethodCount = minMethods,
                MinimumMemberCount = minMembers
            }
        });

    [Fact]
    public async Task BothMethodsAccessSharedField_LCOM5Zero_NoDiagnostic()
    {
        // k=2, l=1, a=1+1=2 → LCOM5 = (2−2)/(1−2) = 0/−1 = 0.0 ≤ 0.5
        const string source = """
            class C {
                private int _x;
                public void Set(int x) { _x = x; }
                public int Get() { return _x; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task DisjointFieldAccess_LCOM5One_TriggersDiagnostic()
    {
        // k=2, l=2, each method accesses only its own field.
        // a=1+1=2 → LCOM5 = (2−4)/(2−4) = −2/−2 = 1.0 > 0.5
        const string source = """
            class C {
                private int _x;
                private int _y;
                public void SetX(int x) { _x = x; }
                public void SetY(int y) { _y = y; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task PartialOverlap_LCOM5Below1_NoDiagnostic()
    {
        // k=3, l=2, method1 accesses {_x,_y}, method2 accesses {_x}, method3 accesses {_y}.
        // a=2+1+1=4 → LCOM5 = (4−6)/(2−6) = −2/−4 = 0.5; NOT > 0.5 → no diagnostic.
        const string source = """
            class C {
                private int _x;
                private int _y;
                public void SetBoth(int x, int y) { _x = x; _y = y; }
                public int GetX() { return _x; }
                public int GetY() { return _y; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task BelowMinimumMethodCount_Skipped_NoDiagnostic()
    {
        const string source = """
            class C {
                private int _x;
                public void SetX(int x) { _x = x; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task BelowMinimumMemberCount_Skipped_NoDiagnostic()
    {
        // No tracked members → l=0 < minimum 1 → analysis is skipped.
        const string source = """
            class C {
                public void A() { }
                public void B() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task StaticMethodsExcluded_DoNotInflateK()
    {
        // Without static method: k=2, l=1, LCOM5=0 → no diagnostic.
        // If static were counted: k=3, l=1, denominator=1−3=−2, a=2, LCOM5=(2−3)/(−2)=0.5 — borderline.
        // Verifying static is excluded by expecting no diagnostic even with threshold=0.0:
        // k=2, l=1, a=2, LCOM5=0 → not > 0.0 → no diagnostic.
        const string source = """
            class C {
                private int _x;
                public void Set(int x) { _x = x; }
                public int Get() { return _x; }
                public static int Utility(int a) { return a * 2; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0.0));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task AutoPropertyTracked_DisjointAccess_TriggersDiagnostic()
    {
        // If auto-properties were NOT tracked, l=0 → analysis skipped → no diagnostic.
        // With tracking: l=2, k=2, a=2, LCOM5=1 > 0.5 → diagnostic.
        // The diagnostic proves auto-properties are correctly detected as tracked members.
        const string source = """
            class C {
                public int X { get; set; }
                public int Y { get; set; }
                public void SetX(int x) { X = x; }
                public void SetY(int y) { Y = y; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM5);
    }

    [Fact]
    public async Task Diagnostic_ContainsClassName()
    {
        const string source = """
            class LowCohesionClass {
                private int _x;
                private int _y;
                public void SetX(int x) { _x = x; }
                public void SetY(int y) { _y = y; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.LCOM5);
        Assert.Contains("LowCohesionClass", diag.GetMessage());
    }
}
