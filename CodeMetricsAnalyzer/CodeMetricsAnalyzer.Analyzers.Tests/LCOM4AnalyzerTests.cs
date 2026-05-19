using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// Tests for LCOM4Analyzer.
///
/// LCOM4 = number of connected components in the method graph, where two methods
/// are connected if they share an accessed member or one calls the other directly.
/// Default threshold is 4 (diagnostic when components > 4).
/// Minimum: 2 ordinary non-static methods and 1 tracked member.
/// </summary>
public class LCOM4AnalyzerTests
{
    private static LCOM4Analyzer CreateAnalyzer(int threshold = 4, int minMethods = 2, int minMembers = 1) =>
        new(new AnalyzerConfiguration
        {
            LCOM4Analysis = new LCOM4AnalysisConfiguration
            {
                CohesionThreshold = threshold,
                MinimumMethodCount = minMethods,
                MinimumMemberCount = minMembers
            }
        });

    [Fact]
    public async Task CohesiveClass_SingleComponent_NoDiagnostic()
    {
        // SetBoth shares _x with GetX and _y with GetY, connecting all three methods.
        // LCOM4 = 1, not > 4.
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
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
    }

    [Fact]
    public async Task FiveDisconnectedGroups_LCOM4Five_TriggersDiagnostic()
    {
        // 10 methods in 5 isolated pairs, each pair sharing a unique field. LCOM4 = 5 > 4.
        const string source = """
            class Scattered {
                private int _a, _b, _c, _d, _e;
                public void SetA(int v) { _a = v; }
                public int GetA() { return _a; }
                public void SetB(int v) { _b = v; }
                public int GetB() { return _b; }
                public void SetC(int v) { _c = v; }
                public int GetC() { return _c; }
                public void SetD(int v) { _d = v; }
                public int GetD() { return _d; }
                public void SetE(int v) { _e = v; }
                public int GetE() { return _e; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
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
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
    }

    [Fact]
    public async Task BelowMinimumMemberCount_Skipped_NoDiagnostic()
    {
        // No tracked members → below minimum → analysis is skipped.
        const string source = """
            class C {
                public void MethodA() { }
                public void MethodB() { }
                public void MethodC() { }
                public void MethodD() { }
                public void MethodE() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
    }

    [Fact]
    public async Task StaticMethodsExcluded_DoNotContributeComponents()
    {
        // Without the static method, there are 2 disconnected groups (LCOM4 = 2).
        // The isolated static method must not be counted as a third component.
        const string source = """
            class C {
                private int _x;
                private int _y;
                public void SetX(int x) { _x = x; }
                public int GetX() { return _x; }
                public void SetY(int y) { _y = y; }
                public int GetY() { return _y; }
                public static void DoNothing() { }
            }
            """;
        // threshold=1: if static were included it might push LCOM4 above threshold
        // Here LCOM4 should remain 2 (two field-sharing pairs)
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 1));
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
        // Verify it reports exactly 2 components in the message (not 3)
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.LCOM4);
        Assert.Contains("2", diag.GetMessage());
    }

    [Fact]
    public async Task MethodsBridgedBySharedMember_SingleComponent_NoDiagnostic()
    {
        // SetX and SetY each access disjoint fields, but SetBoth accesses BOTH _x and _y
        // directly, bridging all three methods into one component via shared-member edges.
        // LCOM4 = 1; threshold=1 means 1 > 1 is false → no diagnostic.
        const string source = """
            class C {
                private int _x;
                private int _y;
                public void SetX(int x) { _x = x; }
                public void SetY(int y) { _y = y; }
                public void SetBoth(int x, int y) { _x = x; _y = y; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 1));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);
    }

    [Fact]
    public async Task AutoPropertyAccess_ConnectsMethods_NoDiagnostic()
    {
        // Three auto-property pairs accessed by two methods each, threshold lowered to 2.
        // WITHOUT auto-property tracking methods would have no shared members → LCOM4=6 > 2.
        // WITH tracking, each pair is connected → LCOM4=3 > 2 → still triggers.
        // Use threshold=5 to assert tracking works (LCOM4=3 not > 5 → no diagnostic).
        const string source = """
            class C {
                public int A { get; set; }
                public int B { get; set; }
                public int C2 { get; set; }
                public void SetA(int v) { A = v; }
                public int GetA() { return A; }
                public void SetB(int v) { B = v; }
                public int GetB() { return B; }
                public void SetC2(int v) { C2 = v; }
                public int GetC2() { return C2; }
            }
            """;
        // With tracking: 3 components (one per auto-property pair); 3 NOT > 5 → no diagnostic.
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 5));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.LCOM4);

        // With threshold=2: 3 > 2 → diagnostic should appear (proves components are counted).
        var diagnosticsLowThreshold = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 2));
        Assert.Contains(diagnosticsLowThreshold, d => d.Id == DiagnosticIdentifiers.LCOM4);
    }

    [Fact]
    public async Task Diagnostic_ContainsClassName()
    {
        const string source = """
            class HighlyIncoherentClass {
                private int _a, _b, _c, _d, _e;
                public void SetA(int v) { _a = v; }
                public int GetA() { return _a; }
                public void SetB(int v) { _b = v; }
                public int GetB() { return _b; }
                public void SetC(int v) { _c = v; }
                public int GetC() { return _c; }
                public void SetD(int v) { _d = v; }
                public int GetD() { return _d; }
                public void SetE(int v) { _e = v; }
                public int GetE() { return _e; }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.LCOM4);
        Assert.Contains("HighlyIncoherentClass", diag.GetMessage());
    }
}
