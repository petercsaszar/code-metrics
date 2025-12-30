# Gitlab group project downloader and analyzer
This tools written in Python finds milestones in students projects by searching for a project in a subgroup that has the correct milestone (the Levenshtein distance is the smallest to predifined milestone names) with due date defined. After that it performes the code metrics calculations on the found commits. The tool is also capable of analyzing open-source projects.

## Usage
### Requirements
Installed `python3` and `dotnet`, optionally `unity`.

### Configuration
Create a `config.yml` file. An example configuration (`config.example.yml`) is provided. The GitLab url (`url`), access token(`token`) and the id for the main group (found in the url when accessing the group from browser, `group_id`) need to be updated. Analysing a single group is possible by filling the `subgroup_id` with the subgroup name like above.

### Usage (on Windows)
1. Open `Developer Powershell for VS 2022` from this folder.
2. Build the dotnet project: 

    ```shell
    dotnet build ../CodeMetricsAnalyzer/CodeMetricsAnalyzer
    ```
3. Create and start a python virtual environment: 
    ```shell
    python -m venv .venv
    .venv/Scripts/activate
    ```
4. Install requirements:
    
    ```shell
    pip install -r requirements.txt
    ```

5. Start analysis: 
    ```shell
    python analyzer.py
    ```
    or for public projects:
    ```shell
    python public_project_analyzer.py
    ```
6. The results will be saved in json files separated by milestones: `analysis_results_x.json`.

### Usage (on Linux, not fully supported)
1. Open a terminal from this folder.
2. Build the dotnet project:

    ```shell
    dotnet build ../CodeMetricsAnalyzer/CodeMetricsAnalyzer
    ```

3. Create and start a python virtual environment: ``

     ```shell
    python3 -m venv .venv
    source .venv/bin/activate
    ```

4. Install requirements:
    
    ```shell
    pip install -r requirements.txt
    ```

5. Start analysis: 
    ```shell
    python3 analyzer.py
    ```
    or for public projects:
    ```shell
    python3 public_project_analyzer.py
    ```
6. The results will be saved in json files separated by milestones: `analysis_results_x.json`.

### Visualize results
The results can be visualized using the jupyter notebooks found in the `visualization` folder. Start the python virtual environment mentioned above and run `jupyter notebook` to start a notebook.

### Docker workflow
- Build the base image once from the project root: `docker build -t code-metrics-analyzer -f docker/Dockerfile .`
- Run `python public_project_analyzer.py` on the host. The script now spawns a fresh `code-metrics-analyzer` container for every commit/version it evaluates, installing any extra .NET SDKs and workloads on demand inside that container.
- To execute a single analysis manually (Windows): `docker run --rm --volume="${pwd}:/workspace" --workdir=/workspace/bulk_analyzer --env ANALYZER_CONFIG=/workspace/bulk_analyzer/config.yml --env CONFIG_PATH=/workspace/bulk_analyzer/config.yml --env PYTHONPATH=/workspace --entrypoint /opt/venv/bin/python code-metrics-analyzer -m bulk_analyzer.container_runner --repo-path /workspace/bulk_analyzer/public_repos/<repo>`
- Containers stream their diagnostic logs to stderr and return metrics as JSON to stdout. The host script aggregates the results and writes the familiar JSON outputs.

### Environment variables

The analyzer and the container orchestration use several environment variables and build-args you can set to control behaviour. Defaults are shown where applicable.

- **ANALYZER_CONFIG / CONFIG_PATH**: Path to the YAML configuration file used by the analyzer. When running inside the official image these are set to `/opt/bulk_analyzer/config.yml` (see `docker/Dockerfile`). If not set, the code falls back to `config.yml` in the current working directory.
- **DOCKER_IMAGE**: Override the Docker image name used by `public_project_analyzer.py` when spawning containers. Default: value from the config `docker.image` or `code-metrics-analyzer`.
- **MSBUILD_PATH**: Path or command to the MSBuild/dotnet binary to use (e.g. `dotnet`). Default: `dotnet`.
- **ANALYSIS_LOGFILE**: Path where container run failures and error details are appended. Default: `analysis_errors.log` in the workspace root unless overridden.
- **DUMP_CONTAINER_OUTPUT**: When set to `1`, `true`, or `True` the orchestrator will append full container STDOUT/STDERR to `ANALYSIS_LOGFILE` even on successful runs (useful for debugging noisy containers).
- **LOG_LEVEL**: Logging verbosity for the Python code (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `INFO`.
- **BUNDLED_ANALYZER_PATH**: Path where the published CodeMetricsAnalyzer DLL is expected inside the image (used as a fallback when the analyzer project is not mounted). Default: `/opt/CodeMetricsAnalyzer`.
- **PYTHONPATH**: Not required by the analyzer itself but useful when bind-mounting your workspace into the image so Python can import the `bulk_analyzer` package (examples in this README use `--env PYTHONPATH=/workspace`).

Build-time argument and runtime variables for .NET installation:

- **DOTNET_INSTALL_URL** (build-arg): When building the Docker image you can pass `--build-arg DOTNET_INSTALL_URL=...` to control which `dotnet-install.sh` is placed into the image. Default: `https://dot.net/v1/dotnet-install.sh`. Example:

```bash
docker build --build-arg DOTNET_INSTALL_URL=dotnet-install.sh -t code-metrics-analyzer -f docker/Dockerfile .
```

- **DOTNET_INSTALL_SCRIPT**: Runtime override for the location of the `dotnet-install.sh` script (used by `dotnet_environment.py`). Default: `/usr/local/bin/dotnet-install.sh`.
- **DOTNET_INSTALL_DIR**: Directory where `dotnet-install.sh` will install SDKs when invoked. Default: `/usr/share/dotnet`.

Notes:
- Prefer environment variables for per-run overrides (CI, Docker, Kubernetes). Keep a versioned `config.yml` in the repo for stable defaults and to document analyzer settings.
- If you enable dynamic SDK installation, ensure `DOTNET_INSTALL_SCRIPT` exists in the image (see `DOTNET_INSTALL_URL` build-arg above) so `ensure_dotnet_environment()` can automatically install SDKs and workloads required by the repository under analysis.

#### Debian / Linux - install and debug
Follow these steps on a Debian-based system to build the image, run one analysis, and debug interactively.

1) Install Docker (if not present):

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io
sudo usermod -aG docker $USER
# Log out and back in (or run `newgrp docker`) to use docker without sudo
```

2) Build the image (from repository root):

```bash
docker build -t code-metrics-analyzer -f docker/Dockerfile .
```

3) Run a single repo analysis (non-interactive):

```bash
docker run --rm --mount type=bind,source="$(pwd)",target=/workspace \
    -w /workspace/bulk_analyzer \
    --env ANALYZER_CONFIG=/workspace/bulk_analyzer/config.yml \
    --env CONFIG_PATH=/workspace/bulk_analyzer/config.yml \
    --env PYTHONPATH=/workspace \
    --entrypoint /opt/venv/bin/python \
    code-metrics-analyzer -m bulk_analyzer.container_runner --repo-path /workspace/bulk_analyzer/public_repos/ravendb_ravendb
```

4) Interactive debug inside container:

```bash
docker run --rm -it --mount type=bind,source="$(pwd)",target=/workspace \
    -w /workspace/bulk_analyzer --entrypoint bash code-metrics-analyzer
# in container shell:
/opt/venv/bin/python -m bulk_analyzer.container_runner --repo-path /workspace/bulk_analyzer/public_repos/ravendb_ravendb
# or run individual checks:
dotnet --info
cd /workspace/bulk_analyzer/public_repos/ravendb_ravendb
dotnet restore path/to/solution.sln
dotnet build path/to/solution.sln -v:detailed
```

5) Run the host orchestrator (spawns per-repo containers):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r bulk_analyzer/requirements.txt
python bulk_analyzer/public_project_analyzer.py
```

Notes
- Use `--mount` (preferred) on Linux to avoid bind mount quoting issues.
- If you see `/opt/venv/bin/python: cannot execute binary file`, inspect the binary with `file /opt/venv/bin/python` and consider using `/usr/bin/python3` or recreating the virtualenv inside the container (`python3 -m venv /opt/venv`).
- If analysis appears stuck, run interactively and run the slow `dotnet` commands manually to see prompts or detailed progress.
