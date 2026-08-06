"""
Code Metrics Analyzer - Bulk analysis orchestration module.

Supports two analysis modes:
  1. Milestone-based analysis (analyzer.py) - Compare code quality across milestones
  2. Latest snapshot analysis (latest_snapshot_analyzer.py) - Analyze HEAD with thresholds
"""

__version__ = "2.0.0"
__all__ = ["analyzer", "latest_snapshot_analyzer"]
