# Akamai ML-Operator

## Prerequisites

Install `uv` to set up the project. `uv venv` sets up the virtual environment.
All dependencies should be exclusively managed using this tool.

## Scripts

A few utility commands are set up using `poe`. Outside the virtual environment,
`poe` can be invoked using `uv run poe <utility>`.

* `test`: runs all tests
* `lint`: checks on formatting
* `format`: fixes formatting
* `export-deps`: regenerates the requirements.txt in `dependencies/`

## Structure

```
ml-operator
|-> chart         # Helm chart for deployment
|-> dependencies  # Generated requirements.txt for image generation
|-> src           # ml-operator package
|-> tests         # pytest modules and resources
```
