using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// Tests for ClassCouplingAnalyzer.
///
/// Coupling = number of distinct non-primitive, non-BCL types a class depends on,
/// collected from: base class, interfaces, field/property/event/method types,
/// type constraints, and all type references within method/property/field bodies.
/// The class itself and its containing types are excluded.
/// Default threshold is 15 (diagnostic when coupling > 15).
/// </summary>
public class ClassCouplingAnalyzerTests
{
    private static ClassCouplingAnalyzer CreateAnalyzer(int threshold = 15) =>
        new(new AnalyzerConfiguration
        {
            ClassCouplingAnalysis = new ClassCouplingAnalysisConfiguration
            {
                MaximumClassCoupling = threshold
            }
        });

    [Fact]
    public async Task ClassWithPrimitiveFieldsOnly_NoDiagnostic()
    {
        // All BCL special types are excluded; coupling = 0.
        const string source = """
            class C {
                int _a;
                string _b;
                bool _c;
                double _d;
                long _e;
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task FifteenCustomTypes_AtThreshold_NoDiagnostic()
    {
        // coupling = 15, NOT > 15 → no diagnostic.
        const string source = """
            class T1 {} class T2 {} class T3 {} class T4 {} class T5 {}
            class T6 {} class T7 {} class T8 {} class T9 {} class T10 {}
            class T11 {} class T12 {} class T13 {} class T14 {} class T15 {}
            class Subject {
                T1 _1; T2 _2; T3 _3; T4 _4; T5 _5;
                T6 _6; T7 _7; T8 _8; T9 _9; T10 _10;
                T11 _11; T12 _12; T13 _13; T14 _14; T15 _15;
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task SixteenCustomTypes_AboveThreshold_TriggersDiagnostic()
    {
        // coupling = 16 > 15 → diagnostic.
        const string source = """
            class T1 {} class T2 {} class T3 {} class T4 {} class T5 {}
            class T6 {} class T7 {} class T8 {} class T9 {} class T10 {}
            class T11 {} class T12 {} class T13 {} class T14 {} class T15 {}
            class T16 {}
            class Subject {
                T1 _1; T2 _2; T3 _3; T4 _4; T5 _5;
                T6 _6; T7 _7; T8 _8; T9 _9; T10 _10;
                T11 _11; T12 _12; T13 _13; T14 _14; T15 _15;
                T16 _16;
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task BaseClass_CountedAsCoupling()
    {
        // The base class is a non-primitive type dependency.
        const string source = """
            class Base { }
            class Derived : Base {
                void M() { }
            }
            """;
        // threshold=0: coupling=1 (Base) > 0 → diagnostic
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0));
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task SelfReference_NotCounted()
    {
        // References to the class itself must be excluded.
        const string source = """
            class Node {
                Node _next;
                public Node GetNext() { return _next; }
                public void SetNext(Node n) { _next = n; }
            }
            """;
        // Self-reference excluded → coupling = 0 → no diagnostic even at threshold=0
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 0));
        Assert.DoesNotContain(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task MethodBodyTypes_CountedAsCoupling()
    {
        // Types used inside a method body (local variables, object creation) also count.
        const string source = """
            class Dep1 { public int Value; }
            class Dep2 { public int Value; }
            class Subject {
                void M() {
                    var d1 = new Dep1();
                    var d2 = new Dep2();
                    int x = d1.Value + d2.Value;
                }
            }
            """;
        // threshold=1: 2 dependencies > 1 → diagnostic
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer(threshold: 1));
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task StructIsAnalyzed()
    {
        // ClassAnalyzer also covers structs.
        const string source = """
            class T1 {} class T2 {} class T3 {} class T4 {} class T5 {}
            class T6 {} class T7 {} class T8 {} class T9 {} class T10 {}
            class T11 {} class T12 {} class T13 {} class T14 {} class T15 {}
            class T16 {}
            struct Subject {
                T1 _1; T2 _2; T3 _3; T4 _4; T5 _5;
                T6 _6; T7 _7; T8 _8; T9 _9; T10 _10;
                T11 _11; T12 _12; T13 _13; T14 _14; T15 _15;
                T16 _16;
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        Assert.Contains(diagnostics, d => d.Id == DiagnosticIdentifiers.ClassCoupling);
    }

    [Fact]
    public async Task Diagnostic_ContainsClassNameAndCouplingCount()
    {
        const string source = """
            class T1 {} class T2 {} class T3 {} class T4 {} class T5 {}
            class T6 {} class T7 {} class T8 {} class T9 {} class T10 {}
            class T11 {} class T12 {} class T13 {} class T14 {} class T15 {}
            class T16 {}
            class HighlyCoupledClass {
                T1 _1; T2 _2; T3 _3; T4 _4; T5 _5;
                T6 _6; T7 _7; T8 _8; T9 _9; T10 _10;
                T11 _11; T12 _12; T13 _13; T14 _14; T15 _15;
                T16 _16;
                void M() { }
            }
            """;
        var diagnostics = await RoslynTestHelper.GetAnalyzerDiagnosticsAsync(source, CreateAnalyzer());
        var diag = diagnostics.First(d => d.Id == DiagnosticIdentifiers.ClassCoupling);
        var message = diag.GetMessage();
        Assert.Contains("HighlyCoupledClass", message);
        Assert.Contains("16", message);
    }
}
