# Gitlab group project downloader and analyzer
This tools written in Python finds milestones in students projects by searching for a project in a subgroup that has the correct milestone (the Levenshtein distance is the smallest to predifined milestone names) with due date defined. After that it performes the code metrics calculations on the found commits.

## Usage
### Requirements
Installed `python3` and `dotnet`.

### Configuration
Create a `config.yml` file. An example configuration (`config.example.yml`) is provided. The GitLab url (`url`), access token(`token`) and the id for the main group (found in the url when accessing the group from browser, `group_id`) need to be updated. Analysing a single group is possible by filling the `subgroup_id` with the subgroup name like above.

### Usage (on Windows)
1. Open a terminal from this folder.
2. Build the dotnet project: `dotnet build ../CodeMetricsAnalyzer/CodeMetricsAnalyzer`
3. Create a python virtual environment: `python -m venv .venv`
4. Start the environment: `.venv/Scripts/activate`
5. Install requirements: `pip install -r requirements.txt`
6. Start analysis: `python analyse.py`
7. The results will be saved in json files separated by milestones: `analysis_results_x.json`.

### Visualize results
The results can be visualized using the `visualize.ipynb` jupyter notebook. Start the python virtual environment mentioned above and run `jupyter notebook` to start a notebook.
