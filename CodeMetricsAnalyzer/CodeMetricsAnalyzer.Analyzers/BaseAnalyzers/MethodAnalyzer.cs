using System.Threading;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;

namespace CodeMetricsAnalyzer.Analyzers.BaseAnalyzers
{
    public abstract class MethodAnalyzer : BaseCodeMetricsAnalyzer
    {
        public MethodAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override void Initialize(AnalysisContext context)
        {
            context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
            context.EnableConcurrentExecution();
            context.RegisterSyntaxNodeAction(AnalyzeMethod,
                SyntaxKind.MethodDeclaration,
                SyntaxKind.ConstructorDeclaration,
                SyntaxKind.GetAccessorDeclaration,
                SyntaxKind.SetAccessorDeclaration,
                SyntaxKind.InitAccessorDeclaration);
        }

        protected abstract void AnalyzeMethod(SyntaxNodeAnalysisContext context);

        /// <summary>
        /// Extracts the identifier token, body, expression-body, and parameter list from a
        /// MethodDeclaration, ConstructorDeclaration, or AccessorDeclaration node.
        /// Returns false for unrecognised nodes or accessors with no body at all.
        /// </summary>
        protected static bool TryGetMemberComponents(
            SyntaxNode node,
            out SyntaxToken identifier,
            out BlockSyntax body,
            out ArrowExpressionClauseSyntax expressionBody,
            out ParameterListSyntax parameterList)
        {
            switch (node)
            {
                case MethodDeclarationSyntax method:
                    identifier = method.Identifier;
                    body = method.Body;
                    expressionBody = method.ExpressionBody;
                    parameterList = method.ParameterList;
                    return true;

                case ConstructorDeclarationSyntax ctor:
                    identifier = ctor.Identifier;
                    body = ctor.Body;
                    expressionBody = ctor.ExpressionBody;
                    parameterList = ctor.ParameterList;
                    return true;

                case AccessorDeclarationSyntax accessor:
                    identifier = accessor.Keyword;
                    body = accessor.Body;
                    expressionBody = accessor.ExpressionBody;
                    parameterList = null;
                    return body != null || expressionBody != null;

                default:
                    identifier = default(SyntaxToken);
                    body = null;
                    expressionBody = null;
                    parameterList = null;
                    return false;
            }
        }

        /// <summary>
        /// Returns the root IOperation for the body of a method, constructor, or accessor.
        /// Prefers the IMethodBodyBaseOperation API; falls back to getting the operation
        /// directly from the body or expression-body syntax node.
        /// </summary>
        protected static IOperation GetMemberOperation(
            SemanticModel model,
            SyntaxNode node,
            CancellationToken cancellationToken)
        {
            switch (node)
            {
                case MethodDeclarationSyntax method:
                {
                    var bodyOp = model.GetOperation(method, cancellationToken) as IMethodBodyOperation;
                    IOperation root = bodyOp?.BlockBody ?? (IOperation)bodyOp?.ExpressionBody;
                    if (root == null && method.Body != null)
                        root = model.GetOperation(method.Body, cancellationToken);
                    if (root == null && method.ExpressionBody?.Expression != null)
                        root = model.GetOperation(method.ExpressionBody.Expression, cancellationToken);
                    return root;
                }

                case ConstructorDeclarationSyntax ctor:
                {
                    var bodyOp = model.GetOperation(ctor, cancellationToken) as IConstructorBodyOperation;
                    IOperation root = bodyOp?.BlockBody ?? (IOperation)bodyOp?.ExpressionBody;
                    if (root == null && ctor.Body != null)
                        root = model.GetOperation(ctor.Body, cancellationToken);
                    if (root == null && ctor.ExpressionBody?.Expression != null)
                        root = model.GetOperation(ctor.ExpressionBody.Expression, cancellationToken);
                    return root;
                }

                case AccessorDeclarationSyntax accessor:
                {
                    if (accessor.Body != null)
                        return model.GetOperation(accessor.Body, cancellationToken);
                    if (accessor.ExpressionBody?.Expression != null)
                        return model.GetOperation(accessor.ExpressionBody.Expression, cancellationToken);
                    return null;
                }

                default:
                    return null;
            }
        }
    }
}
