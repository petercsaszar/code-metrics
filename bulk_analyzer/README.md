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
