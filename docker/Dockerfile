# Multi-stage Dockerfile that builds the .NET analyzer and bundles the Python analyzer
# with integrated MSBuild, cloc, and optional Unity CLI support for turnkey analysis.

# Stage 1: build and publish the CodeMetricsAnalyzer
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy only the analyzer project and restore/publish
COPY CodeMetricsAnalyzer/ ./CodeMetricsAnalyzer/
RUN dotnet restore CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln
RUN dotnet publish CodeMetricsAnalyzer/CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj -c Release -o /app/publish

# Stage 2: runtime image with dotnet SDK, MSBuild, cloc, Python, and optional Unity CLI
FROM mcr.microsoft.com/dotnet/sdk:8.0
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies: Python, cloc, git, optional Unity+mono
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        cloc \
        git \
        ca-certificates \
        wget \
        mono-complete \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Optional: Download and install Unity Editor CLI via build-arg
# Pass --build-arg UNITY_INSTALL_SCRIPT=<base64-encoded-or-url> to include Unity
ARG UNITY_DOWNLOAD_URL=""
RUN if [ -n "$UNITY_DOWNLOAD_URL" ]; then \
        wget -O /tmp/unity_installer.sh "$UNITY_DOWNLOAD_URL" && \
        chmod +x /tmp/unity_installer.sh && \
        /bin/bash /tmp/unity_installer.sh || true; \
    fi

# Copy published dotnet analyzer
COPY --from=build /app/publish /opt/CodeMetricsAnalyzer

# Copy python analyzer package
COPY bulk_analyzer /opt/bulk_analyzer

# Copy entrypoint script
COPY docker/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

WORKDIR /opt/bulk_analyzer

# Create venv and install python deps
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONPATH=/opt

# Default analyzer config and entrypoint
ENV ANALYZER_CONFIG=/opt/bulk_analyzer/config.yml
ENV CONFIG_PATH=/opt/bulk_analyzer/config.yml
# UNITY_PATH defaults to the value in config.yml (analyzer.unity_path)
# Can be overridden by setting -e UNITY_PATH=<path> at runtime or mounting a host Unity installation
ENV UNITY_PATH=""
ENV CLOC_PATH=cloc

# Entrypoint wrapper: reads config.yml to auto-configure UNITY_PATH if mounted, then runs analyzer.py
ENTRYPOINT ["/opt/entrypoint.sh"]
