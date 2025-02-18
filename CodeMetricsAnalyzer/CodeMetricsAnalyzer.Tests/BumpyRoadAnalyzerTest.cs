using System.Threading.Tasks;
using Microsoft.CodeAnalysis.Testing;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Testing;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Testing.Verifiers;
using Xunit;
using CodeMetricsAnalyzer.Analyzers;

namespace CodeMetricsAnalyzer.Tests
{
    public class BumpyRoadAnalyzerTests
    {
        private async Task VerifyCodeAsync(string code, params DiagnosticResult[] expectedDiagnostics)
        {
            // var test = new CSharpAnalyzerTest<BumpyRoadAnalyzer, XUnitVerifier>
            var test = new CSharpAnalyzerTest<BumpyRoadAnalyzer, DefaultVerifier>
            {
                TestCode = code
            };

            test.ExpectedDiagnostics.AddRange(expectedDiagnostics);
            await test.RunAsync();
        }



        [Fact]
        public async Task Test_FlatMethod_NoWarning()
        {
            string testCode = @"
            using System;

            class TestClass
            {
                void FlatMethod()
                {
                    int a = 5;
                    int b = 10;
                    a += b;
                    Console.WriteLine(a);
                }
            }";

            await VerifyCodeAsync(testCode);
        }

        [Fact]
        public async Task Test_SlightlyNestedMethod_NoWarning()
        {
            string testCode = @"
            class TestClass
            {
                void SlightlyNested()
                {
                    int a = 5;
                    if (a > 3)
                    {
                        a += 2;
                    }
                }
            }";

            await VerifyCodeAsync(testCode);
        }

        [Fact]
        public async Task Test_DeeplyNestedMethod_TriggersWarning()
        {
            string testCode = @"
            using System;
            
            class TestClass
            {
                void DeeplyNested()
                {
                    for (int i = 0; i < 10; i++)
                    {
                        if (i % 2 == 0)
                        {
                            while (i < 5)
                            {
                                Console.WriteLine(i);
                            }
                        }
                    }
                }
            }";

            var expectedDiagnostic = new DiagnosticResult("BR001", DiagnosticSeverity.Warning)
                .WithLocation(6, 22)
                .WithMessage("Method 'DeeplyNested' has a high bumpy road score (4.00). Consider refactoring deeply nested structures.");

            await VerifyCodeAsync(testCode, expectedDiagnostic);
        }

        [Fact]
        public async Task Test_EmptyMethod_WarningWithScoreOne()
        {
            string testCode = @"
            class TestClass
            {
                void EmptyMethod()
                {
                }
            }";

            await VerifyCodeAsync(testCode);
        }

        [Fact]
        public async Task Test_ModerateNesting_BorderlineCase()
        {
            string testCode = @"
            using System;

            class TestClass
            {
                void ModerateNesting()
                {
                    if (true)
                    {
                        if (true)
                        {
                            Console.WriteLine(""Nested"");
                        }
                    }
                }
            }";

            var expectedDiagnostic = new DiagnosticResult("BR001", DiagnosticSeverity.Warning)
                .WithLocation(6, 22)
                .WithMessage("Method 'ModerateNesting' has a high bumpy road score (3.00). Consider refactoring deeply nested structures.");

            await VerifyCodeAsync(testCode, expectedDiagnostic);
        }
    }
}
