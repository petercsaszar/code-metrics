# Gitlab group project downloader and analyzer
This tools written in Python finds milestones in students projects by searching for a project in a subgroup that has the correct milestone (the Levenshtein distance is the smallest to predifined milestone names) with due date defined. After that it performes the code metrics calculations on the found commits.

## Usage
### Requirements
Python 3, and the following packages: requests, python-gitlab, gitpython, fuzzywuzzy, python-Levenshtein.

### Configuration
Create a `config.yml` file. An example configuration (`config.example.yml`) is provided. The GitLab url (`url`), access token(`token`) and the id for the main group (found in the url when accessing the group from browser, `group_id`) need to be updated. Analysing a single group is possible by filling the `subgroup_id` with the subgroup name like above.

### Starting the analysis
Execute `python analyse.py` from command promt. The results will be saved in json files separated by milestones: `analysis_results_x.json`.
