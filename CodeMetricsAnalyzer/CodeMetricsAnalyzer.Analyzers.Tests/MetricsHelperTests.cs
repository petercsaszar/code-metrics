using CodeMetricsAnalyzer.Analyzers.Tests.Helpers;
using Xunit;

namespace CodeMetricsAnalyzer.Analyzers.Tests;

/// <summary>
/// Unit tests for MetricsHelper — CalculateLinesOfCode, CalculateCyclomaticComplexity,
/// and CalculateHalsteadVolume. Each test works with a real Roslyn compilation so the
/// IOperation trees are genuine.
/// </summary>
public class MetricsHelperTests
{
    // -------------------------------------------------------------------------
    // Lines of Code
    // -------------------------------------------------------------------------

    [Fact]
    public void LinesOfCode_ExpressionBodyMethod_ReturnsOne()
    {
        const string source = """
            class C {
                int Add(int a, int b) => a + b;
            }
            """;
        var (_, method) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(1, MetricsHelper.CalculateLinesOfCode(method));
    }

    [Fact]
    public void LinesOfCode_SingleLineBlockBody_ReturnsOne()
    {
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var (_, method) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(1, MetricsHelper.CalculateLinesOfCode(method));
    }

    [Fact]
    public void LinesOfCode_ThreeLineBlockBody_ReturnsThree()
    {
        // Body spans three lines: opening brace, return statement, closing brace.
        const string source = """
            class C {
                int Add(int a, int b)
                {
                    return a + b;
                }
            }
            """;
        var (_, method) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(3, MetricsHelper.CalculateLinesOfCode(method));
    }

    [Fact]
    public void LinesOfCode_FiveLineBlockBody_ReturnsFive()
    {
        const string source = """
            class C {
                int Method(int a, int b)
                {
                    int x = a + 1;
                    int y = b + 2;
                    int z = x * y;
                    return z;
                }
            }
            """;
        var (_, method) = RoslynTestHelper.GetFirstMethodOperation(source);
        // { ... } spans: {, x=, y=, z=, return, } = 6 lines
        Assert.Equal(6, MetricsHelper.CalculateLinesOfCode(method));
    }

    // -------------------------------------------------------------------------
    // Cyclomatic Complexity
    // -------------------------------------------------------------------------

    [Fact]
    public void CC_SimpleMethod_BaselineOne()
    {
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(1, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_SingleIf_ReturnsTwo()
    {
        const string source = """
            class C {
                int Max(int a, int b) {
                    if (a > b) return a;
                    return b;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(2, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_IfElseIf_ReturnsThree()
    {
        const string source = """
            class C {
                int Sign(int a) {
                    if (a > 0) return 1;
                    else if (a < 0) return -1;
                    return 0;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(3, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_SwitchDefaultOnly_DoesNotAddBranch()
    {
        // The `default` clause must NOT be counted as a decision point.
        const string source = """
            class C {
                string GetLabel(int x) {
                    switch (x) {
                        default: return "other";
                    }
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(1, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_SwitchThreeCasesAndDefault_ReturnsFour()
    {
        // Three non-default case clauses + baseline = 4.
        // The default clause must not add a branch.
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
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(4, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_ForLoop_ReturnsTwo()
    {
        const string source = """
            class C {
                int Sum(int n) {
                    int s = 0;
                    for (int i = 0; i < n; i++) s += i;
                    return s;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(2, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_WhileLoop_ReturnsTwo()
    {
        const string source = """
            class C {
                int Sum(int n) {
                    int s = 0;
                    while (n > 0) { s += n; n--; }
                    return s;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(2, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_LogicalAnd_AddsOneBranch()
    {
        const string source = """
            class C {
                bool BothPositive(int a, int b) {
                    return a > 0 && b > 0;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(2, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    [Fact]
    public void CC_LogicalOr_AddsOneBranch()
    {
        const string source = """
            class C {
                bool EitherPositive(int a, int b) {
                    return a > 0 || b > 0;
                }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(2, MetricsHelper.CalculateCyclomaticComplexity(op!));
    }

    // -------------------------------------------------------------------------
    // Halstead Volume
    // -------------------------------------------------------------------------

    [Fact]
    public void Halstead_EmptyMethod_ReturnsZero()
    {
        const string source = """
            class C {
                void M() { }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(0.0, MetricsHelper.CalculateHalsteadVolume(op!));
    }

    [Fact]
    public void Halstead_ReturnAddition_ReturnsEight()
    {
        // Operators: "return", "Add" → n1=2, N1=2
        // Operands:  "a", "b"        → n2=2, N2=2
        // Volume = (N1+N2) * log2(n1+n2) = 4 * log2(4) = 4 * 2 = 8.0
        const string source = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        Assert.Equal(8.0, MetricsHelper.CalculateHalsteadVolume(op!), precision: 10);
    }

    [Fact]
    public void Halstead_RepeatedOperand_CountsDistinctVocabulary()
    {
        // { return a + a; }
        // Operators: "return", "Add" → n1=2, N1=2
        // Operands:  "a" (used twice, distinct once) → n2=1, N2=2
        // Volume = 4 * log2(3) ≈ 6.340
        const string source = """
            class C {
                int Double(int a) { return a + a; }
            }
            """;
        var (op, _) = RoslynTestHelper.GetFirstMethodOperation(source);
        double expected = 4.0 * Math.Log(3, 2);
        Assert.Equal(expected, MetricsHelper.CalculateHalsteadVolume(op!), precision: 10);
    }

    [Fact]
    public void Halstead_MoreBranches_ProducesHigherVolume()
    {
        // A method with branches accumulates more operators, so volume must grow.
        const string simple = """
            class C {
                int Simple(int a, int b) { return a + b; }
            }
            """;
        const string branched = """
            class C {
                int Branched(int a, int b) {
                    if (a > b) return a;
                    return b;
                }
            }
            """;
        var (simpleOp, _) = RoslynTestHelper.GetFirstMethodOperation(simple);
        var (branchedOp, _) = RoslynTestHelper.GetFirstMethodOperation(branched);

        Assert.True(
            MetricsHelper.CalculateHalsteadVolume(branchedOp!) >
            MetricsHelper.CalculateHalsteadVolume(simpleOp!));
    }

    [Fact]
    public void Halstead_ExpressionBody_LowerThanEquivalentBlockBody()
    {
        // Expression-bodied methods produce an implicit IReturnOperation (IsImplicit=true)
        // which is skipped, giving lower volume than the explicit-return block form.
        // This test documents the current known difference so regressions are visible.
        const string blockBody = """
            class C {
                int Add(int a, int b) { return a + b; }
            }
            """;
        const string exprBody = """
            class C {
                int Add(int a, int b) => a + b;
            }
            """;
        var (blockOp, _) = RoslynTestHelper.GetFirstMethodOperation(blockBody);
        var (exprOp, _) = RoslynTestHelper.GetFirstMethodOperation(exprBody);

        double blockVolume = MetricsHelper.CalculateHalsteadVolume(blockOp!);
        double exprVolume = MetricsHelper.CalculateHalsteadVolume(exprOp!);

        // Block body: operators {"return","Add"}, operands {"a","b"} → V=8.0
        Assert.Equal(8.0, blockVolume, precision: 10);
        // Expression body: the implicit return is skipped → lower volume
        Assert.True(exprVolume < blockVolume,
            $"Expected expression body volume ({exprVolume:F3}) < block body volume ({blockVolume:F3})");
    }
}
