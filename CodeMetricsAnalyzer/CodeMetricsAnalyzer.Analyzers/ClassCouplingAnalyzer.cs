using System.Collections.Generic;
using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class ClassCouplingAnalyzer : DiagnosticAnalyzer
    {
        private readonly AnalyzerConfiguration _config;

        public ClassCouplingAnalyzer(AnalyzerConfiguration config)
        {
            _config = config;
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.ClassCouplingRule);

        public override void Initialize(AnalysisContext context)
        {
            context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
            context.EnableConcurrentExecution();

            context.RegisterSyntaxNodeAction(AnalyzeMethod, SyntaxKind.MethodDeclaration);
            context.RegisterSyntaxNodeAction(AnalyzeClass, SyntaxKind.ClassDeclaration);
        }

        private void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;

            var methodSymbol = semanticModel.GetDeclaredSymbol(methodDeclaration, context.CancellationToken);
            if (methodSymbol is null)
                return;

            var coupledTypes = new HashSet<INamedTypeSymbol>(SymbolEqualityComparer.Default);

            AddCoupledType(coupledTypes, methodSymbol.ReturnType);

            foreach (var parameter in methodSymbol.Parameters)
            {
                AddCoupledType(coupledTypes, parameter.Type);
            }

            foreach (var typeParameter in methodSymbol.TypeParameters)
            {
                foreach (var constraintType in typeParameter.ConstraintTypes)
                {
                    AddCoupledType(coupledTypes, constraintType);
                }
            }

            foreach (var attribute in methodSymbol.GetAttributes())
            {
                AddCoupledType(coupledTypes, attribute.AttributeClass);
            }

            foreach (var attribute in methodSymbol.GetReturnTypeAttributes())
            {
                AddCoupledType(coupledTypes, attribute.AttributeClass);
            }

            if (methodDeclaration.Body != null)
            {
                var bodyOperation = semanticModel.GetOperation(methodDeclaration.Body, context.CancellationToken);
                if (bodyOperation != null)
                {
                    CollectCoupledTypesFromOperation(bodyOperation, coupledTypes);
                }
            }

            if (methodDeclaration.ExpressionBody != null)
            {
                var expressionOperation = semanticModel.GetOperation(methodDeclaration.ExpressionBody.Expression, context.CancellationToken);
                if (expressionOperation != null)
                {
                    CollectCoupledTypesFromOperation(expressionOperation, coupledTypes);
                }
            }

            RemoveContainingTypes(methodSymbol, coupledTypes);

            int coupling = coupledTypes.Count;

            if (coupling > _config.ClassCouplingAnalysis.MaximumClassCoupling)
            {
                var diagnostic = Diagnostic.Create(
                    DiagnosticDescriptors.ClassCouplingRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    coupling);

                context.ReportDiagnostic(diagnostic);
            }
        }

        private void AnalyzeClass(SyntaxNodeAnalysisContext context)
        {
            var classDeclaration = (ClassDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;

            var classSymbol = semanticModel.GetDeclaredSymbol(classDeclaration, context.CancellationToken);
            if (classSymbol is null)
                return;

            var coupledTypes = new HashSet<INamedTypeSymbol>(SymbolEqualityComparer.Default);

            AddCoupledType(coupledTypes, classSymbol.BaseType);

            foreach (var implementedInterface in classSymbol.Interfaces)
            {
                AddCoupledType(coupledTypes, implementedInterface);
            }

            foreach (var typeParameter in classSymbol.TypeParameters)
            {
                foreach (var constraintType in typeParameter.ConstraintTypes)
                {
                    AddCoupledType(coupledTypes, constraintType);
                }
            }

            foreach (var attribute in classSymbol.GetAttributes())
            {
                AddCoupledType(coupledTypes, attribute.AttributeClass);
            }

            foreach (var member in classSymbol.GetMembers())
            {
                switch (member)
                {
                    case IFieldSymbol field:
                        AddCoupledType(coupledTypes, field.Type);
                        break;

                    case IPropertySymbol property:
                        AddCoupledType(coupledTypes, property.Type);
                        foreach (var parameter in property.Parameters)
                        {
                            AddCoupledType(coupledTypes, parameter.Type);
                        }
                        break;

                    case IEventSymbol @event:
                        AddCoupledType(coupledTypes, @event.Type);
                        break;

                    case IMethodSymbol method:
                        AddCoupledType(coupledTypes, method.ReturnType);

                        foreach (var parameter in method.Parameters)
                        {
                            AddCoupledType(coupledTypes, parameter.Type);
                        }

                        foreach (var typeParameter in method.TypeParameters)
                        {
                            foreach (var constraintType in typeParameter.ConstraintTypes)
                            {
                                AddCoupledType(coupledTypes, constraintType);
                            }
                        }

                        foreach (var attribute in method.GetAttributes())
                        {
                            AddCoupledType(coupledTypes, attribute.AttributeClass);
                        }

                        foreach (var attribute in method.GetReturnTypeAttributes())
                        {
                            AddCoupledType(coupledTypes, attribute.AttributeClass);
                        }

                        break;
                }
            }

            foreach (var memberSyntax in classDeclaration.Members)
            {
                switch (memberSyntax)
                {
                    case MethodDeclarationSyntax methodDeclaration:
                        {
                            if (methodDeclaration.Body != null)
                            {
                                var bodyOperation = semanticModel.GetOperation(methodDeclaration.Body, context.CancellationToken);
                                if (bodyOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(bodyOperation, coupledTypes);
                                }
                            }

                            if (methodDeclaration.ExpressionBody != null)
                            {
                                var expressionOperation = semanticModel.GetOperation(methodDeclaration.ExpressionBody.Expression, context.CancellationToken);
                                if (expressionOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(expressionOperation, coupledTypes);
                                }
                            }

                            break;
                        }

                    case PropertyDeclarationSyntax propertyDeclaration:
                        {
                            if (propertyDeclaration.ExpressionBody != null)
                            {
                                var expressionOperation = semanticModel.GetOperation(propertyDeclaration.ExpressionBody.Expression, context.CancellationToken);
                                if (expressionOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(expressionOperation, coupledTypes);
                                }
                            }

                            if (propertyDeclaration.AccessorList != null)
                            {
                                foreach (var accessor in propertyDeclaration.AccessorList.Accessors)
                                {
                                    var accessorOperation = semanticModel.GetOperation(accessor, context.CancellationToken);
                                    if (accessorOperation != null)
                                    {
                                        CollectCoupledTypesFromOperation(accessorOperation, coupledTypes);
                                    }
                                }
                            }

                            break;
                        }

                    case IndexerDeclarationSyntax indexerDeclaration:
                        {
                            if (indexerDeclaration.ExpressionBody != null)
                            {
                                var expressionOperation = semanticModel.GetOperation(indexerDeclaration.ExpressionBody.Expression, context.CancellationToken);
                                if (expressionOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(expressionOperation, coupledTypes);
                                }
                            }

                            if (indexerDeclaration.AccessorList != null)
                            {
                                foreach (var accessor in indexerDeclaration.AccessorList.Accessors)
                                {
                                    var accessorOperation = semanticModel.GetOperation(accessor, context.CancellationToken);
                                    if (accessorOperation != null)
                                    {
                                        CollectCoupledTypesFromOperation(accessorOperation, coupledTypes);
                                    }
                                }
                            }

                            break;
                        }

                    case EventDeclarationSyntax eventDeclaration:
                        {
                            if (eventDeclaration.AccessorList != null)
                            {
                                foreach (var accessor in eventDeclaration.AccessorList.Accessors)
                                {
                                    var accessorOperation = semanticModel.GetOperation(accessor, context.CancellationToken);
                                    if (accessorOperation != null)
                                    {
                                        CollectCoupledTypesFromOperation(accessorOperation, coupledTypes);
                                    }
                                }
                            }

                            break;
                        }

                    case ConstructorDeclarationSyntax constructorDeclaration:
                        {
                            if (constructorDeclaration.Body != null)
                            {
                                var bodyOperation = semanticModel.GetOperation(constructorDeclaration.Body, context.CancellationToken);
                                if (bodyOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(bodyOperation, coupledTypes);
                                }
                            }

                            if (constructorDeclaration.ExpressionBody != null)
                            {
                                var expressionOperation = semanticModel.GetOperation(constructorDeclaration.ExpressionBody.Expression, context.CancellationToken);
                                if (expressionOperation != null)
                                {
                                    CollectCoupledTypesFromOperation(expressionOperation, coupledTypes);
                                }
                            }

                            break;
                        }
                }
            }

            RemoveContainingTypes(classSymbol, coupledTypes);

            int coupling = coupledTypes.Count;

            if (coupling > _config.ClassCouplingAnalysis.MaximumClassCoupling)
            {
                var diagnostic = Diagnostic.Create(
                    DiagnosticDescriptors.ClassCouplingRule,
                    classDeclaration.Identifier.GetLocation(),
                    classDeclaration.Identifier.Text,
                    coupling);

                context.ReportDiagnostic(diagnostic);
            }
        }

        private void CollectCoupledTypesFromOperation(
            IOperation rootOperation,
            HashSet<INamedTypeSymbol> coupledTypes)
        {
            foreach (var operation in rootOperation.DescendantsAndSelf())
            {
                if (operation.IsImplicit)
                    continue;

                AddCoupledType(coupledTypes, operation.Type);

                switch (operation)
                {
                    case IVariableDeclarationGroupOperation variableDeclarationGroup:
                        foreach (var declaration in variableDeclarationGroup.Declarations)
                        {
                            foreach (var declarator in declaration.Declarators)
                            {
                                AddCoupledType(coupledTypes, declarator.Symbol?.Type);
                            }
                        }
                        break;

                    case IInvocationOperation invocation:
                        AddCoupledType(coupledTypes, invocation.TargetMethod?.ContainingType);
                        AddCoupledType(coupledTypes, invocation.TargetMethod?.ReturnType);
                        foreach (var parameter in invocation.TargetMethod.Parameters)
                        {
                            AddCoupledType(coupledTypes, parameter.Type);
                        }
                        break;

                    case IObjectCreationOperation objectCreation:
                        AddCoupledType(coupledTypes, objectCreation.Type);
                        AddCoupledType(coupledTypes, objectCreation.Constructor?.ContainingType);
                        break;

                    case IPropertyReferenceOperation propertyReference:
                        AddCoupledType(coupledTypes, propertyReference.Property?.ContainingType);
                        AddCoupledType(coupledTypes, propertyReference.Property?.Type);
                        break;

                    case IFieldReferenceOperation fieldReference:
                        AddCoupledType(coupledTypes, fieldReference.Field?.ContainingType);
                        AddCoupledType(coupledTypes, fieldReference.Field?.Type);
                        break;

                    case IEventReferenceOperation eventReference:
                        AddCoupledType(coupledTypes, eventReference.Event?.ContainingType);
                        AddCoupledType(coupledTypes, eventReference.Event?.Type);
                        break;

                    case IMemberReferenceOperation memberReference:
                        AddCoupledType(coupledTypes, memberReference.Member?.ContainingType);
                        break;

                    case ILocalReferenceOperation localReference:
                        AddCoupledType(coupledTypes, localReference.Local?.Type);
                        break;

                    case IParameterReferenceOperation parameterReference:
                        AddCoupledType(coupledTypes, parameterReference.Parameter?.Type);
                        break;

                    case IArrayCreationOperation arrayCreation:
                        AddCoupledType(coupledTypes, arrayCreation.Type);
                        break;

                    case IConversionOperation conversion:
                        AddCoupledType(coupledTypes, conversion.Type);
                        AddCoupledType(coupledTypes, conversion.OperatorMethod?.ContainingType);
                        break;

                    case IIsTypeOperation isTypeOperation:
                        AddCoupledType(coupledTypes, isTypeOperation.TypeOperand);
                        break;

                    case ITypeOfOperation typeOfOperation:
                        AddCoupledType(coupledTypes, typeOfOperation.TypeOperand);
                        break;

                    case ICatchClauseOperation catchClause:
                        AddCoupledType(coupledTypes, catchClause.ExceptionType);
                        break;

                    case IDelegateCreationOperation delegateCreation:
                        AddCoupledType(coupledTypes, delegateCreation.Type);
                        break;

                    case IThrowOperation throwOperation:
                        AddCoupledType(coupledTypes, throwOperation.Exception?.Type);
                        break;
                }
            }
        }

        private void AddCoupledType(HashSet<INamedTypeSymbol> coupledTypes, ITypeSymbol typeSymbol)
        {
            if (typeSymbol is null)
                return;

            switch (typeSymbol)
            {
                case IArrayTypeSymbol arrayType:
                    AddCoupledType(coupledTypes, arrayType.ElementType);
                    return;

                case IPointerTypeSymbol pointerType:
                    AddCoupledType(coupledTypes, pointerType.PointedAtType);
                    return;

                case IFunctionPointerTypeSymbol functionPointer:
                    return;

                case IDynamicTypeSymbol dynamic:
                    return;

                case INamedTypeSymbol namedType:
                    AddNamedTypeRecursively(coupledTypes, namedType);
                    return;
            }
        }

        private void AddNamedTypeRecursively(HashSet<INamedTypeSymbol> coupledTypes, INamedTypeSymbol type)
        {
            if (IsIgnoredType(type))
                return;

            coupledTypes.Add(type.OriginalDefinition);

            if (type.ContainingType != null)
            {
                AddNamedTypeRecursively(coupledTypes, type.ContainingType);
            }

            foreach (var typeArgument in type.TypeArguments)
            {
                AddCoupledType(coupledTypes, typeArgument);
            }

            if (type.IsTupleType)
            {
                foreach (var tupleElement in type.TupleElements)
                {
                    AddCoupledType(coupledTypes, tupleElement.Type);
                }
            }
        }

        private bool IsIgnoredType(INamedTypeSymbol type)
        {
            if (type.IsAnonymousType)
                return true;

            switch (type.SpecialType)
            {
                case SpecialType.System_Boolean:
                case SpecialType.System_Byte:
                case SpecialType.System_Char:
                case SpecialType.System_Decimal:
                case SpecialType.System_Double:
                case SpecialType.System_Int16:
                case SpecialType.System_Int32:
                case SpecialType.System_Int64:
                case SpecialType.System_UInt16:
                case SpecialType.System_UInt32:
                case SpecialType.System_UInt64:
                case SpecialType.System_IntPtr:
                case SpecialType.System_UIntPtr:
                case SpecialType.System_SByte:
                case SpecialType.System_Single:
                case SpecialType.System_String:
                case SpecialType.System_Object:
                case SpecialType.System_ValueType:
                case SpecialType.System_Void:
                case SpecialType.System_Enum:
                case SpecialType.System_MulticastDelegate:
                case SpecialType.System_Delegate:
                case SpecialType.System_Array:
                case SpecialType.System_Collections_IEnumerable:
                case SpecialType.System_Collections_Generic_IEnumerable_T:
                case SpecialType.System_Collections_Generic_IList_T:
                case SpecialType.System_Collections_Generic_ICollection_T:
                case SpecialType.System_Collections_IEnumerator:
                case SpecialType.System_Collections_Generic_IEnumerator_T:
                case SpecialType.System_Collections_Generic_IReadOnlyList_T:
                case SpecialType.System_Collections_Generic_IReadOnlyCollection_T:
                case SpecialType.System_Nullable_T:
                case SpecialType.System_DateTime:
                case SpecialType.System_Runtime_CompilerServices_IsVolatile:
                case SpecialType.System_IDisposable:
                case SpecialType.System_TypedReference:
                case SpecialType.System_ArgIterator:
                case SpecialType.System_RuntimeArgumentHandle:
                case SpecialType.System_RuntimeFieldHandle:
                case SpecialType.System_RuntimeMethodHandle:
                case SpecialType.System_RuntimeTypeHandle:
                case SpecialType.System_IAsyncResult:
                case SpecialType.System_AsyncCallback:
                case SpecialType.System_Runtime_CompilerServices_RuntimeFeature:
                case SpecialType.System_Runtime_CompilerServices_PreserveBaseOverridesAttribute:
                case SpecialType.System_Runtime_CompilerServices_InlineArrayAttribute:
                    return true;

                case SpecialType.None:
                default:
                    return HasCompilerGeneratedAttribute(type);
            }
        }

        private static bool HasCompilerGeneratedAttribute(INamedTypeSymbol type)
        {
            foreach (var attribute in type.GetAttributes())
            {
                var attributeClass = attribute.AttributeClass;
                if (attributeClass is null)
                    continue;

                var metadataName = attributeClass.ToDisplayString();

                if (metadataName == "System.Runtime.CompilerServices.CompilerGeneratedAttribute" ||
                    metadataName == "System.CodeDom.Compiler.GeneratedCodeAttribute")
                {
                    return true;
                }
            }

            return false;
        }

        private static void RemoveContainingTypes(
            ISymbol symbol,
            HashSet<INamedTypeSymbol> coupledTypes)
        {
            var namedType = symbol as INamedTypeSymbol ?? symbol.ContainingType;

            while (namedType != null)
            {
                coupledTypes.Remove(namedType);
                namedType = namedType.ContainingType;
            }
        }
    }
}