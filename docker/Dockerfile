# Multi-stage Dockerfile — builds the .NET analyzer, then assembles the runtime
# image on top of the official .NET SDK image.
#
# Build:
#   docker build -f docker/Dockerfile -t code-metrics-analyzer .
#
# Run (milestone-based analysis):
#   docker run --rm \
#     -v "$(pwd)/reports:/app/reports" \
#     -e GITLAB_TOKEN=glpat-... \
#     -e GITLAB_URL=https://gitlab.example.com \
#     -e GITLAB_GROUP_ID=42 \
#     -e MILESTONE_1="Sprint 1,Sprint1" \
#     -e MILESTONE_2="Sprint 2" \
#     code-metrics-analyzer
#
# Run (latest snapshot analysis — method-level metrics on HEAD):
#   docker run --rm \
#     -v "$(pwd)/reports:/app/reports" \
#     -e GITLAB_TOKEN=glpat-... \
#     -e GITLAB_URL=https://gitlab.example.com \
#     -e GITLAB_GROUP_ID=42 \
#     -e ANALYSIS_MODE=latest_snapshot \
#     code-metrics-analyzer
#
# Unity projects are handled automatically — a .sln is generated from Assets/
# using pure Python (no Unity editor or license required).

# ─── Stage 1: build and publish the .NET CodeMetricsAnalyzer ─────────────────
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY CodeMetricsAnalyzer/ ./CodeMetricsAnalyzer/
RUN dotnet restore CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln \
 && dotnet publish \
        CodeMetricsAnalyzer/CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj \
        -c Release -o /app/publish --no-restore

# ─── Stage 2: .NET SDK + Python runtime ──────────────────────────────────────
FROM unityci/editor:ubuntu-2020.04-2021.3.21f1
USER root
ENV DEBIAN_FRONTEND=noninteractive

# Install Python, cloc, git, curl, and ca-certificates
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        cloc \
        git \
        curl \
        ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3 /usr/bin/python \
 && ln -sf /usr/bin/pip3 /usr/bin/pip

# Download the official dotnet-install script so dotnet_environment.py can
# install additional SDK/runtime versions required by analysed repositories at runtime.
RUN curl -sSL https://dot.net/v1/dotnet-install.sh -o /usr/local/bin/dotnet-install.sh \
 && chmod +x /usr/local/bin/dotnet-install.sh

# Install .NET 10 runtime+sdk into the Unity image so the analyzer can run
# (the build stage already produced a published output). We use the install
# script to avoid relying on distro packages inside the Unity image.
RUN /usr/local/bin/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet \
 && ln -s /usr/share/dotnet/dotnet /usr/bin/dotnet || true

# Copy the published .NET analyzer from Stage 1
COPY --from=build /app/publish /opt/CodeMetricsAnalyzer

# Copy Python source files (bulk_analyzer/config.yml is excluded via .dockerignore)
COPY bulk_analyzer/analyzer.py \
     bulk_analyzer/latest_snapshot_analyzer.py \
     bulk_analyzer/milestone_commit_finder.py \
     bulk_analyzer/dotnet_environment.py \
     bulk_analyzer/html_report_generator.py \
     bulk_analyzer/container_runner.py \
     bulk_analyzer/method_analyzer.py \
     bulk_analyzer/public_project_analyzer.py \
     bulk_analyzer/threshold_analyzer.py \
     bulk_analyzer/requirements.txt \
     /opt/bulk_analyzer/

# Bake in the example config as the image default.
# Secrets (token, group ID, milestones) must be supplied at runtime via env vars.
COPY bulk_analyzer/config.example.yml /opt/bulk_analyzer/config.yml

# Copy the entrypoint script
COPY docker/entrypoint.sh /opt/entrypoint.sh
RUN sed -i 's/\r$//' /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

WORKDIR /opt/bulk_analyzer

# Create a Python virtual environment and install dependencies
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade --quiet pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# venv must be on PATH; dotnet is already on PATH via the base image
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONPATH=/opt

# Optional: a Unity license file can be provided at runtime by mounting it
# and passing its path using the `UNITY_LICENSE_PATH` environment variable.
# Example: docker run -e UNITY_LICENSE_PATH=/run/secrets/unity.ulf -v /host/path/unity.ulf:/run/secrets/unity.ulf ...

# ── Runtime configuration ─────────────────────────────────────────────────────
# GITLAB_TOKEN must be supplied at runtime via -e GITLAB_TOKEN=...
# It is intentionally not declared here — never bake secrets into the image.

# Optional — fall back to the baked-in config.yml value when not set
ENV GITLAB_URL=""
ENV GITLAB_GROUP_ID=""
ENV GITLAB_SUBGROUP_ID=""

# Milestones — falls back to config.yml; choose one format if overriding:
#   MILESTONE_KEYWORDS  JSON array-of-arrays: '[["Name","Alt"],["Name2"]]'
#   OR numbered vars:   MILESTONE_1="Name,Alt name"   MILESTONE_2="Name2"
ENV MILESTONE_KEYWORDS=""

# Where repositories are cloned inside the container
ENV CLONE_DIR="/tmp/repos"

# Output directory for JSON results and HTML reports (mount a host volume here)
ENV REPORT_OUTPUT="/app/reports"

ENV CLOC_PATH=cloc

# Runtime config is generated by entrypoint.sh from the env vars above.
# Do not override ANALYZER_CONFIG unless you are mounting a hand-crafted config.yml.
ENV ANALYZER_CONFIG=/tmp/runtime-config.yml
ENV CONFIG_PATH=/tmp/runtime-config.yml

# Analysis mode: "milestone" (default) or "latest_snapshot"
# Use "latest_snapshot" to analyze HEAD of each project's default branch instead of milestones.
ENV ANALYSIS_MODE=milestone

# Entrypoint merges config.yml defaults with env-var overrides, then runs analyzer.py
ENTRYPOINT ["/bin/bash", "/opt/entrypoint.sh"]
