using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public sealed class BumpyRoadAnalyzer : MethodAnalyzer
    {
        // A "bump" starts when logic is nested at least two levels deep.
        private const int MinimumBumpDepth = 2;

        public BumpyRoadAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.BumpyRoadRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            if (!(context.Node is MethodDeclarationSyntax methodDeclaration))
                return;

            // Expression-bodied members are a single expression with no nesting,
            // so their bumpy road score is always zero — skip them intentionally.
            var body = methodDeclaration.Body;
            if (body == null || body.Statements.Count == 0)
                return;

            var entries = new List<StatementEntry>();
            CollectStatements(body, currentDepth: 0, entries);

            if (entries.Count == 0)
                return;

            var bumps = DetectBumps(entries);
            if (bumps.Count == 0)
                return;

            double score = CalculateBumpyRoadScore(bumps);

            if (score > _config.BumpyRoadAnalysis.BumpynessThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.BumpyRoadRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    Math.Round(score, 2));
            }
        }

        private static void CollectStatements(
            StatementSyntax statement,
            int currentDepth,
            List<StatementEntry> result)
        {
            switch (statement)
            {
                case BlockSyntax block:
                    foreach (var child in block.Statements)
                        CollectStatements(child, currentDepth, result);
                    break;

                case IfStatementSyntax ifStatement:
                    AddStatement(result, ifStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectStatements(ifStatement.Statement, currentDepth + 1, result);

                    if (ifStatement.Else != null)
                    {
                        // FIX: else-if chains are kept at the same logical nesting level
                        // as the original if, not incremented further. This reflects the
                        // CodeScene model where else-if is a single decision branch, not
                        // true additional nesting.
                        if (ifStatement.Else.Statement is IfStatementSyntax elseIf)
                            CollectStatements(elseIf, currentDepth, result);
                        else
                            CollectStatements(ifStatement.Else.Statement, currentDepth + 1, result);
                    }
                    break;

                case ForStatementSyntax forStatement:
                    AddStatement(result, forStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectStatements(forStatement.Statement, currentDepth + 1, result);
                    break;

                case ForEachStatementSyntax forEachStatement:
                    AddStatement(result, forEachStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectStatements(forEachStatement.Statement, currentDepth + 1, result);
                    break;

                case WhileStatementSyntax whileStatement:
                    AddStatement(result, whileStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectStatements(whileStatement.Statement, currentDepth + 1, result);
                    break;

                case DoStatementSyntax doStatement:
                    AddStatement(result, doStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectStatements(doStatement.Statement, currentDepth + 1, result);
                    break;

                case SwitchStatementSyntax switchStatement:
                    AddStatement(result, switchStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    foreach (var section in switchStatement.Sections)
                    {
                        foreach (var child in section.Statements)
                            CollectStatements(child, currentDepth + 1, result);
                    }
                    break;

                case TryStatementSyntax tryStatement:
                    // FIX: try, catch, and finally all increment depth consistently.
                    // Previously try and finally were collected at currentDepth while
                    // catch was at currentDepth + 1, which was asymmetric and wrong.
                    CollectStatements(tryStatement.Block, currentDepth + 1, result);

                    foreach (var catchClause in tryStatement.Catches)
                        CollectStatements(catchClause.Block, currentDepth + 1, result);

                    if (tryStatement.Finally != null)
                        CollectStatements(tryStatement.Finally.Block, currentDepth + 1, result);
                    break;

                default:
                    AddStatement(result, statement, currentDepth, isControl: false, startsBumpCandidate: false);
                    break;
            }
        }

        private static void AddStatement(
            List<StatementEntry> result,
            StatementSyntax statement,
            int depth,
            bool isControl,
            bool startsBumpCandidate)
        {
            var span = statement.SyntaxTree.GetLineSpan(statement.Span);
            int startLine = span.StartLinePosition.Line;
            int endLine = span.EndLinePosition.Line;

            result.Add(new StatementEntry(
                statement,
                depth,
                isControl,
                startsBumpCandidate,
                startLine,
                endLine));
        }

        private static List<BumpRegion> DetectBumps(List<StatementEntry> statements)
        {
            var ordered = statements
                .OrderBy(s => s.StartLine)
                .ThenBy(s => s.EndLine)
                .ToList();

            var bumps = new List<BumpRegion>();

            foreach (var anchor in ordered.Where(s => s.StartsBumpCandidate && s.Depth >= MinimumBumpDepth))
            {
                var bump = CreateBumpFromAnchor(anchor, ordered);
                if (bump == null)
                    continue;

                // FIX: scan all existing bumps for overlap, not just the last one.
                // The previous check only compared against bumps[bumps.Count - 1],
                // which could miss overlaps with earlier regions when a bump's anchor
                // has a large EndLine that spans multiple subsequent anchors.
                var overlapping = bumps.FirstOrDefault(
                    b => bump.StartLine <= b.EndLine && bump.EndLine >= b.StartLine);

                if (overlapping != null)
                    MergeInto(overlapping, bump);
                else
                    bumps.Add(bump);
            }

            return bumps;
        }

        private static BumpRegion CreateBumpFromAnchor(
            StatementEntry anchor,
            List<StatementEntry> orderedStatements)
        {
            var bumpStatements = orderedStatements
                .Where(s =>
                    s.StartLine >= anchor.StartLine &&
                    s.EndLine <= anchor.EndLine &&
                    s.Depth >= MinimumBumpDepth)
                .ToList();

            if (bumpStatements.Count == 0)
                return null;

            int startLine = bumpStatements.Min(s => s.StartLine);
            int endLine = bumpStatements.Max(s => s.EndLine);

            var bump = new BumpRegion(startLine, endLine);
            bump.Statements.AddRange(bumpStatements);
            return bump;
        }

        private static void MergeInto(BumpRegion target, BumpRegion source)
        {
            target.StartLine = Math.Min(target.StartLine, source.StartLine);
            target.EndLine = Math.Max(target.EndLine, source.EndLine);

            foreach (var statement in source.Statements)
            {
                // FIX: ReferenceEquals alone uniquely identifies a syntax node —
                // the redundant line and depth checks have been removed.
                if (!target.Statements.Any(existing => ReferenceEquals(existing.Statement, statement.Statement)))
                    target.Statements.Add(statement);
            }
        }

        private static double CalculateBumpyRoadScore(List<BumpRegion> bumps)
        {
            if (bumps.Count == 0)
                return 0;

            double total = 0;

            foreach (var bump in bumps)
            {
                // Score each line by the maximum nesting depth active on that line,
                // subtracting the minimum bump depth so that depth=2 contributes 1,
                // depth=3 contributes 2, and so on. This gives a continuous
                // area-under-the-curve measure rather than discrete integer aggregates,
                // producing a much wider spread of scores across methods.
                var maxDepthByLine = bump.Statements
                    .GroupBy(s => s.StartLine)
                    .ToDictionary(g => g.Key, g => g.Max(s => s.Depth));

                double bumpArea = maxDepthByLine.Values
                    .Sum(d => d - (MinimumBumpDepth - 1));

                total += bumpArea;
            }

            // Use log scaling for the multi-bump penalty instead of a fixed step
            // increment. This keeps the penalty continuous and avoids the discrete
            // jumps of (bumps.Count - 1) * 4 that created score bands in the distribution.
            total *= 1.0 + Math.Log(bumps.Count);

            // Normalize to 0–10 so config thresholds are intuitive.
            // Reference worst realistic case: 3 bumps, avg depth 3, 15 lines each
            //   → area per bump = 15 lines * (3 - (2-1)) = 15 * 2 = 30
            //   → total area    = 3 * 30 = 90
            //   → log penalty   = 90 * (1 + ln(3)) ≈ 90 * 2.099 ≈ 189
            //   → normalized    = 10.0
            const double referenceScore = 189.0;
            return Math.Min(10.0, (total / referenceScore) * 10.0);
        }

        private sealed class StatementEntry
        {
            public StatementEntry(
                StatementSyntax statement,
                int depth,
                bool isControl,
                bool startsBumpCandidate,
                int startLine,
                int endLine)
            {
                Statement = statement;
                Depth = depth;
                IsControl = isControl;
                StartsBumpCandidate = startsBumpCandidate;
                StartLine = startLine;
                EndLine = endLine;
            }

            public StatementSyntax Statement { get; }
            public int Depth { get; }
            public bool IsControl { get; }
            public bool StartsBumpCandidate { get; }
            public int StartLine { get; }
            public int EndLine { get; }
        }

        private sealed class BumpRegion
        {
            public BumpRegion(int startLine, int endLine)
            {
                StartLine = startLine;
                EndLine = endLine;
            }

            public int StartLine { get; set; }
            public int EndLine { get; set; }
            public List<StatementEntry> Statements { get; } = new List<StatementEntry>();
        }
    }
}