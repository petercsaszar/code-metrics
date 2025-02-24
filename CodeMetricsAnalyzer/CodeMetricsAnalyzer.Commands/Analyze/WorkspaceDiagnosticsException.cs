using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Commands.Analyze
{
    public class WorkspaceDiagnosticsException : Exception
    {
        public WorkspaceDiagnosticsException()
        {

        }

        public WorkspaceDiagnosticsException(string? message) : base(message)
        {

        }
    }
}
