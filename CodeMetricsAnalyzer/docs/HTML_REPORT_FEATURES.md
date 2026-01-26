# HTML Report Generator

## Overview

The HTML Report Generator creates a comprehensive, interactive HTML report for code metrics analysis results, similar to ReportGenerator but specifically designed for this analyzer's metrics.

## Features

- **Modern, Responsive UI**: Clean and professional interface that works on all devices
- **Multiple Views**:
  - **Home Page**: Overview with summary cards showing total issues, projects analyzed, and issue types
  - **Summary Page**: Aggregated view of all issue types sorted by frequency
  - **Project Pages**: Detailed breakdown of issues per project, organized by file
- **Smart Code Snippets**: Click "Show Code" to view context around each diagnostic
  - **Method-level metrics**: Shows the entire method with attributes and comments
  - **Other metrics**: Shows 3 lines of context before and after
- **Visual Indicators**: Color-coded badges and severity indicators for easy identification
- **Navigation**: Easy navigation between different views

## Usage

Use the `--report-output` option with the analyze command:

```bash
# Generate HTML report in a specific folder
CodeMetricsAnalyzer analyze path/to/solution.sln --report-output ./reports

# Generate both XML output and HTML report
CodeMetricsAnalyzer analyze path/to/project.csproj --output results.xml --report-output ./html-report
```

## Report Structure

The generated report includes:

```
report-output-folder/
??? index.html          # Main entry point with project overview
??? summary.html        # Issue summary grouped by type
??? project_*.html      # Individual project detail pages
??? styles.css          # Stylesheet for all pages
```

## Opening the Report

After generation, simply open `index.html` in any web browser:

```bash
# Windows
start ./reports/index.html

# macOS
open ./reports/index.html

# Linux
xdg-open ./reports/index.html
```

## Report Details

### Home Page
- Summary cards showing key metrics
- List of all analyzed projects with issue counts
- Quick links to project details

### Summary Page
- Aggregated view of all diagnostic types
- Issue frequency counts
- Severity indicators

### Project Pages
- Detailed diagnostics grouped by file
- Line and character position for each issue
- Severity and diagnostic ID information
- Full diagnostic messages
- **Smart code snippets**: Click "Show Code" button to reveal/hide the code context

## Code Snippet Feature

Each diagnostic in the project detail pages includes a "Show Code" button with intelligent context display:

### Method-Level Metrics (e.g., Cyclomatic Complexity, Parameter Count)
When the diagnostic is about a method, the **entire method** is shown:
- Method signature with attributes
- XML documentation comments (if present)
- Complete method body
- Highlighted line showing where the diagnostic was triggered
- Line numbers for easy reference

Example for "Method has too many parameters":
```csharp
/// <summary>
/// Calculates complex business logic
/// </summary>
[Obsolete]
public async Task<Result> CalculateAsync(
    int param1, string param2, bool param3, 
    DateTime param4, List<int> param5, 
    object param6, decimal param7)      ? Highlighted
{
    // ... entire method body shown ...
    return result;
}
```

### Other Diagnostics (e.g., Class-level metrics)
Shows **3 lines of context** before and after:
- The problematic line (highlighted with ? marker)
- 3 lines before for context
- 3 lines after for context
- Line numbers for easy reference

Example:
```csharp
  15 | using System.Linq;
  16 | 
  17 | namespace MyNamespace
  18 | {
? 19 |     public class MyClass          ? Highlighted
  20 |     {
  21 |         private int field1;
  22 |         private string field2;
```

### Visual Features
- **Dark theme** for better code readability
- **Syntax highlighting** via monospace font
- **Highlighted line** with background color and ? marker
- **Line numbers** aligned for easy reference
- **Collapsible** - click to show/hide without cluttering the report

## Customization

The generated `styles.css` can be customized to match your organization's branding or preferences. The report uses:
- CSS Grid and Flexbox for responsive layouts
- Modern color scheme with gradient cards
- Professional typography
- Hover effects and visual feedback
- Dark theme for code snippets
