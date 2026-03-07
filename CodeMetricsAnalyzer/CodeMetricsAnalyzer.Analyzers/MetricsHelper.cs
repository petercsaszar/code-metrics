using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Operations;
using System;
using System.Collections.Generic;
using System.Text;

namespace CodeMetricsAnalyzer.Analyzers
{
    public static class MetricsHelper
    {
        public static bool HasConditionalLogic(IOperation operation)
        {
            switch (operation.Kind)
            {
                case OperationKind.CaseClause:
                case OperationKind.Coalesce:
                case OperationKind.Conditional:
                case OperationKind.ConditionalAccess:
                case OperationKind.Loop:
                    return true;

                case OperationKind.BinaryOperator:
                    var binaryOperation = (IBinaryOperation)operation;
                    return binaryOperation.OperatorKind == BinaryOperatorKind.ConditionalAnd ||
                           binaryOperation.OperatorKind == BinaryOperatorKind.ConditionalOr ||
                           (binaryOperation.Type?.SpecialType == SpecialType.System_Boolean &&
                            (binaryOperation.OperatorKind == BinaryOperatorKind.Or ||
                             binaryOperation.OperatorKind == BinaryOperatorKind.And));

                default:
                    return false;
            }
        }

        public static int CalculateCyclomaticComplexity(IOperation operationRoot)
        {
            // Baseline +1 for an executable body
            int cyclomaticComplexity = 1;

            foreach (var op in operationRoot.DescendantsAndSelf())
            {
                if (op.IsImplicit)
                    continue;

                if (HasConditionalLogic(op))
                    cyclomaticComplexity++;
            }

            return cyclomaticComplexity;
        }

        public static double CalculateHalsteadVolume(IOperation rootOperation)
        {
            var distinctOperators = new HashSet<string>(StringComparer.Ordinal);
            var distinctOperands = new HashSet<string>(StringComparer.Ordinal);
            int totalOperators = 0;
            int totalOperands = 0;

            foreach (var operation in rootOperation.DescendantsAndSelf())
            {
                if (operation.IsImplicit)
                    continue;

                if (TryGetOperator(operation, out var operatorText))
                {
                    distinctOperators.Add(operatorText);
                    totalOperators++;
                }

                if (TryGetOperand(operation, out var operandText))
                {
                    distinctOperands.Add(operandText);
                    totalOperands++;
                }
            }

            int n1 = distinctOperators.Count;
            int n2 = distinctOperands.Count;
            int N1 = totalOperators;
            int N2 = totalOperands;

            int vocabulary = n1 + n2;
            int length = N1 + N2;

            if (vocabulary == 0 || length == 0)
                return 0;

            return length * Math.Log(vocabulary, 2);
        }

        private static bool TryGetOperator(IOperation operation, out string operatorText)
        {
            switch (operation)
            {
                case IBinaryOperation binary:
                    operatorText = binary.OperatorKind.ToString();
                    return true;

                case IUnaryOperation unary:
                    operatorText = unary.OperatorKind.ToString();
                    return true;

                case IConditionalOperation conditional:
                    operatorText = "?:";
                    return true;

                case ICoalesceOperation coalesce:
                    operatorText = "??";
                    return true;

                case IInvocationOperation invocation:
                    operatorText = invocation.TargetMethod.Name;
                    return true;

                case IAssignmentOperation assignment:
                    operatorText = assignment.Kind.ToString();
                    return true;

                case IIncrementOrDecrementOperation incDec:
                    operatorText = incDec.Kind.ToString();
                    return true;

                case ILoopOperation loop:
                    operatorText = loop.LoopKind.ToString();
                    return true;

                case IBranchOperation branch:
                    operatorText = branch.BranchKind.ToString();
                    return true;

                case IReturnOperation returnOp:
                    operatorText = "return";
                    return true;

                default:
                    operatorText = string.Empty;
                    return false;
            }
        }

        private static bool TryGetOperand(IOperation operation, out string operandText)
        {
            switch (operation)
            {
                case ILocalReferenceOperation local:
                    operandText = local.Local.Name;
                    return true;

                case IParameterReferenceOperation parameter:
                    operandText = parameter.Parameter.Name;
                    return true;

                case IFieldReferenceOperation field:
                    operandText = field.Field.Name;
                    return true;

                case IPropertyReferenceOperation property:
                    operandText = property.Property.Name;
                    return true;

                case ILiteralOperation literal:
                    operandText = literal.ConstantValue.HasValue && literal.ConstantValue.Value != null
                        ? literal.ConstantValue.Value.ToString()
                        : "null";
                    return true;

                default:
                    operandText = string.Empty;
                    return false;
            }
        }

        public static int CalculateLinesOfCode(MethodDeclarationSyntax method)
        {
            SyntaxNode syntaxToMeasure = (SyntaxNode)method.Body ?? (SyntaxNode)method.ExpressionBody ?? method;
            var lineSpan = syntaxToMeasure.SyntaxTree.GetLineSpan(syntaxToMeasure.Span);

            return Math.Max(1, lineSpan.EndLinePosition.Line - lineSpan.StartLinePosition.Line + 1);
        }
    }
}
