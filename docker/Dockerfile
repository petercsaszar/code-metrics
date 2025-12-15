# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:8.0

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        git \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && git config --global --add safe.directory '*'

RUN curl -sSL https://dot.net/v1/dotnet-install.sh -o /usr/local/bin/dotnet-install.sh \
    && chmod +x /usr/local/bin/dotnet-install.sh

WORKDIR /app

COPY bulk_analyzer/requirements.txt bulk_analyzer/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r bulk_analyzer/requirements.txt

COPY . .

RUN chmod +x docker/scripts/run_public_analysis.sh

ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="/opt/venv/bin:${PATH}:/usr/share/dotnet"
ENV DOTNET_INSTALL_DIR=/usr/share/dotnet

ENTRYPOINT ["bash"]
