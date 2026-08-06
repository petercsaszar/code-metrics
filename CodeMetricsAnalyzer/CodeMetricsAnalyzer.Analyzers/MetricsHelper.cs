using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Operations;
using System;
using System.Collections.Generic;

namespace CodeMetricsAnalyzer.Analyzers
{
    public static class MetricsHelper
    {
        public static bool HasConditionalLogic(IOperation operation)
        {
            switch (operation.Kind)
            {
                case OperationKind.SwitchExpressionArm:
                case OperationKind.CatchClause:
                case OperationKind.Coalesce:
                case OperationKind.Conditional:
                case OperationKind.ConditionalAccess:
                case OperationKind.Loop:
                    return true;

                // Count case clauses except default — default is the "else" path in McCabe's model.
                case OperationKind.CaseClause:
                    return !(operation is IDefaultCaseClauseOperation);

                case OperationKind.BinaryOperator:
                    var binaryOp = (IBinaryOperation)operation;
                    return binaryOp.OperatorKind == BinaryOperatorKind.ConditionalAnd ||
                           binaryOp.OperatorKind == BinaryOperatorKind.ConditionalOr;

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

                case IConditionalOperation _:
                    operatorText = "?:";
                    return true;

                case ICoalesceOperation _:
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

                case IReturnOperation _:
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

        /// <summary>
        /// Counts logical lines of code (executable statements) for a method, constructor, or
        /// property accessor body — matching Visual Studio's definition, which excludes blank
        /// lines, comments, and braces.
        /// </summary>
        public static int CalculateLinesOfCode(SyntaxNode memberNode)
        {
            BlockSyntax body = null;
            bool hasExpressionBody = false;

            switch (memberNode)
            {
                case MethodDeclarationSyntax m:
                    body = m.Body;
                    hasExpressionBody = m.ExpressionBody != null;
                    break;
                case ConstructorDeclarationSyntax c:
                    body = c.Body;
                    hasExpressionBody = c.ExpressionBody != null;
                    break;
                case AccessorDeclarationSyntax a:
                    body = a.Body;
                    hasExpressionBody = a.ExpressionBody != null;
                    break;
            }

            if (body != null)
            {
                int count = 0;
                foreach (var node in body.DescendantNodes())
                {
                    if (node is StatementSyntax && !(node is BlockSyntax))
                        count++;
                }
                return Math.Max(1, count);
            }

            return hasExpressionBody ? 1 : 0;
        }

        /// <summary>
        /// Collects instance field and property accesses from within an operation tree,
        /// restricted to members of <paramref name="containingType"/>.
        /// This is used by LCOM analyzers instead of DataFlowAnalysis, which does not
        /// see auto-property backing fields accessed through property syntax.
        /// </summary>
        public static void CollectMemberAccesses(
            IOperation rootOperation,
            HashSet<ISymbol> accessedMembers,
            INamedTypeSymbol containingType)
        {
            foreach (var op in rootOperation.DescendantsAndSelf())
            {
                if (op is IFieldReferenceOperation fieldRef)
                {
                    if (!fieldRef.Field.IsStatic &&
                        !fieldRef.Field.IsImplicitlyDeclared &&
                        SymbolEqualityComparer.Default.Equals(
                            fieldRef.Field.ContainingType.OriginalDefinition,
                            containingType.OriginalDefinition))
                    {
                        accessedMembers.Add(fieldRef.Field.OriginalDefinition);
                    }
                }
                else if (op is IPropertyReferenceOperation propRef)
                {
                    if (!propRef.Property.IsStatic &&
                        !propRef.Property.IsIndexer &&
                        SymbolEqualityComparer.Default.Equals(
                            propRef.Property.ContainingType.OriginalDefinition,
                            containingType.OriginalDefinition))
                    {
                        accessedMembers.Add(propRef.Property.OriginalDefinition);
                    }
                }
            }
        }

        /// <summary>
        /// Returns the count of instance members (non-static explicit fields + non-static
        /// non-indexer properties) that are tracked for LCOM calculations.
        /// Auto-property backing fields (IsImplicitlyDeclared) are excluded to avoid
        /// double-counting alongside their corresponding property.
        /// </summary>
        public static int GetTrackedMemberCount(INamedTypeSymbol typeSymbol)
        {
            int count = 0;
            foreach (var member in typeSymbol.GetMembers())
            {
                if (member is IFieldSymbol field && !field.IsStatic && !field.IsImplicitlyDeclared)
                    count++;
                else if (member is IPropertySymbol property && !property.IsStatic && !property.IsIndexer)
                    count++;
            }
            return count;
        }
    }
}
