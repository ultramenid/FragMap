"""Jupyter server config: notebooks in this project are saved without outputs,
so every time the notebook is opened it starts fresh.

Loaded automatically when Jupyter runs from this project's .venv (linked into
.venv/etc/jupyter), or explicitly with: jupyter lab --config=src/jupyter_server_config.py
"""


def strip_outputs(model, **kwargs):
    """Pre-save hook: drop outputs, execution counts and saved widget state."""
    if model.get("type") != "notebook" or model.get("content") is None:
        return
    nb = model["content"]
    nb.get("metadata", {}).pop("widgets", None)
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None


# `c` is provided by Jupyter. jupyter-server prints a harmless "Overriding existing pre_save_hook
# (strip_outputs) with a new one (strip_outputs)" warning at startup: its validator runs twice.
c.ContentsManager.pre_save_hook = strip_outputs  # noqa: F821
