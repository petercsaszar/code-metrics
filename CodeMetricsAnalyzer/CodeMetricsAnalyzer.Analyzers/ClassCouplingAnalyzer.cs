using System.Collections.Generic;
using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class ClassCouplingAnalyzer : ClassAnalyzer
    {
        public ClassCouplingAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.ClassCouplingRule);

        protected override void AnalyzeClass(SyntaxNodeAnalysisContext context)
        {
            var classDeclaration = (ClassDeclarationSyntax)context.Node;
            var semanticModel = context.SemanticModel;

            var classSymbol = semanticModel.GetDeclaredSymbol(classDeclaration, context.CancellationToken) as INamedTypeSymbol;
            if (classSymbol == null)
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
                var field = member as IFieldSymbol;
                if (field != null)
                {
                    AddCoupledType(coupledTypes, field.Type);
                    continue;
                }

                var property = member as IPropertySymbol;
                if (property != null)
                {
                    AddCoupledType(coupledTypes, property.Type);
                    foreach (var parameter in property.Parameters)
                    {
                        AddCoupledType(coupledTypes, parameter.Type);
                    }

                    continue;
                }

                var eventSymbol = member as IEventSymbol;
                if (eventSymbol != null)
                {
                    AddCoupledType(coupledTypes, eventSymbol.Type);
                    continue;
                }

                var method = member as IMethodSymbol;
                if (method != null)
                {
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
                }
            }

            foreach (var memberSyntax in classDeclaration.Members)
            {
                var methodDeclaration = memberSyntax as MethodDeclarationSyntax;
                if (methodDeclaration != null)
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

                    continue;
                }

                var propertyDeclaration = memberSyntax as PropertyDeclarationSyntax;
                if (propertyDeclaration != null)
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

                    continue;
                }

                var indexerDeclaration = memberSyntax as IndexerDeclarationSyntax;
                if (indexerDeclaration != null)
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

                    continue;
                }

                var eventDeclaration = memberSyntax as EventDeclarationSyntax;
                if (eventDeclaration != null)
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

                    continue;
                }

                var constructorDeclaration = memberSyntax as ConstructorDeclarationSyntax;
                if (constructorDeclaration != null)
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

                var variableDeclarationGroup = operation as IVariableDeclarationGroupOperation;
                if (variableDeclarationGroup != null)
                {
                    foreach (var declaration in variableDeclarationGroup.Declarations)
                    {
                        foreach (var declarator in declaration.Declarators)
                        {
                            AddCoupledType(coupledTypes, declarator.Symbol != null ? declarator.Symbol.Type : null);
                        }
                    }

                    continue;
                }

                var invocation = operation as IInvocationOperation;
                if (invocation != null)
                {
                    AddCoupledType(coupledTypes, invocation.TargetMethod != null ? invocation.TargetMethod.ContainingType : null);
                    AddCoupledType(coupledTypes, invocation.TargetMethod != null ? invocation.TargetMethod.ReturnType : null);

                    if (invocation.TargetMethod != null)
                    {
                        foreach (var parameter in invocation.TargetMethod.Parameters)
                        {
                            AddCoupledType(coupledTypes, parameter.Type);
                        }
                    }

                    continue;
                }

                var objectCreation = operation as IObjectCreationOperation;
                if (objectCreation != null)
                {
                    AddCoupledType(coupledTypes, objectCreation.Type);
                    AddCoupledType(coupledTypes, objectCreation.Constructor != null ? objectCreation.Constructor.ContainingType : null);
                    continue;
                }

                var propertyReference = operation as IPropertyReferenceOperation;
                if (propertyReference != null)
                {
                    AddCoupledType(coupledTypes, propertyReference.Property != null ? propertyReference.Property.ContainingType : null);
                    AddCoupledType(coupledTypes, propertyReference.Property != null ? propertyReference.Property.Type : null);
                    continue;
                }

                var fieldReference = operation as IFieldReferenceOperation;
                if (fieldReference != null)
                {
                    AddCoupledType(coupledTypes, fieldReference.Field != null ? fieldReference.Field.ContainingType : null);
                    AddCoupledType(coupledTypes, fieldReference.Field != null ? fieldReference.Field.Type : null);
                    continue;
                }

                var eventReference = operation as IEventReferenceOperation;
                if (eventReference != null)
                {
                    AddCoupledType(coupledTypes, eventReference.Event != null ? eventReference.Event.ContainingType : null);
                    AddCoupledType(coupledTypes, eventReference.Event != null ? eventReference.Event.Type : null);
                    continue;
                }

                var memberReference = operation as IMemberReferenceOperation;
                if (memberReference != null)
                {
                    AddCoupledType(coupledTypes, memberReference.Member != null ? memberReference.Member.ContainingType : null);
                    continue;
                }

                var localReference = operation as ILocalReferenceOperation;
                if (localReference != null)
                {
                    AddCoupledType(coupledTypes, localReference.Local != null ? localReference.Local.Type : null);
                    continue;
                }

                var parameterReference = operation as IParameterReferenceOperation;
                if (parameterReference != null)
                {
                    AddCoupledType(coupledTypes, parameterReference.Parameter != null ? parameterReference.Parameter.Type : null);
                    continue;
                }

                var arrayCreation = operation as IArrayCreationOperation;
                if (arrayCreation != null)
                {
                    AddCoupledType(coupledTypes, arrayCreation.Type);
                    continue;
                }

                var conversion = operation as IConversionOperation;
                if (conversion != null)
                {
                    AddCoupledType(coupledTypes, conversion.Type);
                    AddCoupledType(coupledTypes, conversion.OperatorMethod != null ? conversion.OperatorMethod.ContainingType : null);
                    continue;
                }

                var isTypeOperation = operation as IIsTypeOperation;
                if (isTypeOperation != null)
                {
                    AddCoupledType(coupledTypes, isTypeOperation.TypeOperand);
                    continue;
                }

                var typeOfOperation = operation as ITypeOfOperation;
                if (typeOfOperation != null)
                {
                    AddCoupledType(coupledTypes, typeOfOperation.TypeOperand);
                    continue;
                }

                var catchClause = operation as ICatchClauseOperation;
                if (catchClause != null)
                {
                    AddCoupledType(coupledTypes, catchClause.ExceptionType);
                    continue;
                }

                var delegateCreation = operation as IDelegateCreationOperation;
                if (delegateCreation != null)
                {
                    AddCoupledType(coupledTypes, delegateCreation.Type);
                    continue;
                }

                var throwOperation = operation as IThrowOperation;
                if (throwOperation != null)
                {
                    AddCoupledType(coupledTypes, throwOperation.Exception != null ? throwOperation.Exception.Type : null);
                }
            }
        }

        private void AddCoupledType(HashSet<INamedTypeSymbol> coupledTypes, ITypeSymbol typeSymbol)
        {
            if (typeSymbol == null)
                return;

            var arrayType = typeSymbol as IArrayTypeSymbol;
            if (arrayType != null)
            {
                AddCoupledType(coupledTypes, arrayType.ElementType);
                return;
            }

            var pointerType = typeSymbol as IPointerTypeSymbol;
            if (pointerType != null)
            {
                AddCoupledType(coupledTypes, pointerType.PointedAtType);
                return;
            }

            if (typeSymbol is IFunctionPointerTypeSymbol)
                return;

            if (typeSymbol is IDynamicTypeSymbol)
                return;

            var namedType = typeSymbol as INamedTypeSymbol;
            if (namedType != null)
            {
                AddNamedTypeRecursively(coupledTypes, namedType);
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
                if (attributeClass == null)
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