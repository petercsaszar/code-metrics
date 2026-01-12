# Multi-stage Dockerfile that builds the .NET analyzer and bundles the Python analyzer
# Note: Metrics.exe is Windows-only; metrics collection only runs on Windows containers

# Stage 1: build and publish the CodeMetricsAnalyzer
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy only the analyzer project and restore/publish
COPY CodeMetricsAnalyzer/ ./CodeMetricsAnalyzer/
RUN dotnet restore CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln
RUN dotnet publish CodeMetricsAnalyzer/CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj -c Release -o /app/publish

# Stage 2: runtime image with dotnet SDK (required for `dotnet run`) and Python venv
FROM mcr.microsoft.com/dotnet/sdk:8.0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Provide dotnet-install.sh inside the image. By default this downloads the
# official Microsoft script; you can override `DOTNET_INSTALL_URL` at build
# time to point to a local file in the build context (e.g. --build-arg
# DOTNET_INSTALL_URL=dotnet-install.sh) or an alternate URL.
ARG DOTNET_INSTALL_URL=https://dot.net/v1/dotnet-install.sh
ADD ${DOTNET_INSTALL_URL} /usr/local/bin/dotnet-install.sh
RUN chmod +x /usr/local/bin/dotnet-install.sh || true

# Copy published dotnet analyzer
COPY --from=build /app/publish /opt/CodeMetricsAnalyzer

# Copy python analyzer package
COPY bulk_analyzer /opt/bulk_analyzer

WORKDIR /opt/bulk_analyzer

# Create venv and install python deps
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONPATH=/opt

# Default analyzer config and entrypoint (can be overridden by docker run)
ENV ANALYZER_CONFIG=/opt/bulk_analyzer/config.yml
ENV CONFIG_PATH=/opt/bulk_analyzer/config.yml

ENTRYPOINT ["/opt/venv/bin/python", "-m", "bulk_analyzer.container_runner"]
