using System.Xml;
using System.Xml.Linq;

namespace CodeMetricsAnalyzer.ResultExporter;

public class XmlResultExporter : IResultExporter
{
    public async Task ExportResultsAsync(string path, ResultExporterArguments arguments, CancellationToken cancellationToken = default)
    {


        var diagnosticsResults = arguments.ProjectDiagnostics;

        var diagnostics = diagnosticsResults
            .SelectMany(projectDiagnostics => projectDiagnostics.Diagnostics);

        var diagnosticGroups = diagnostics.GroupBy(diagnostic => diagnostic.Id)
            .OrderBy(group => group.Key)
            .Select(group => new XElement(
                "Diagnostic",
                new XAttribute("Id", group.Key),
                new XAttribute("Title", group.First().Title),
                new XAttribute("Count", group.Count()),
                new XElement("Description", group.First().Title)
            ));

        var summaryElement = new XElement(
            "Summary",
            diagnosticGroups
        );

        var projects = diagnosticsResults
            .OrderBy(projectDiagnostics => projectDiagnostics.FilePath)
            .Where(projectDiagnostics => projectDiagnostics.Diagnostics.Count > 0)
            .Select(projectDiagnostics => new XElement(
                "Project",
                new XAttribute("Name", projectDiagnostics.Name),
                new XAttribute("FilePath", projectDiagnostics.FilePath),
                new XElement(
                    "Diagnostics",
                    projectDiagnostics.Diagnostics
                        .OrderBy(diagnostic => diagnostic.FilePath)
                        .ThenBy(diagnostic => diagnostic.Id)
                        .Select(diagnostic => new XElement(
                            "Diagnostic",
                            new XAttribute("Id", diagnostic.Id),
                            new XElement("Severity", diagnostic.Severity),
                            new XElement("Message", diagnostic.Message),
                            new XElement("FilePath", diagnostic.FilePath),
                            new XElement(
                                "Location",
                                new XAttribute("Line", diagnostic.Location.Line),
                                new XAttribute("Character", diagnostic.Location.Character)
                            )
                        ))
                )
            ));

        var projectsElement = new XElement(
            "Projects",
            projects
        );
        
        var document = new XDocument(
            new XElement("CodeMetricsAnalyzer",

                new XElement("CodeAnalysis", summaryElement, projectsElement)
            )
        );

        using (var fileStream = new FileStream(path, FileMode.Create))
        {
            using (var xmlWriter = XmlWriter.Create(fileStream, new XmlWriterSettings { Async = true, Indent = true }))
            {
                await document.SaveAsync(xmlWriter, cancellationToken);
            }
        }
    }
}
