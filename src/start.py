"""Open the notebook fresh: clear its saved outputs, then start JupyterLab with
jupyter_server_config.py so later saves stay output-free too.

    python src/start.py                # clear outputs + open mangrove_fragmentation.ipynb
    python src/start.py --clear        # only clear outputs, don't start Jupyter
    python src/start.py --no-browser ...  # any other options go to `jupyter lab`

Run it with the project's environment (.venv/bin/python src/start.py, or after `source .venv/bin/activate`).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project folder (this file is in src/)
NOTEBOOK = ROOT / "mangrove_fragmentation.ipynb"
CONFIG = Path(__file__).resolve().parent / "jupyter_server_config.py"

try:
    import nbformat
except ImportError:
    sys.exit(f"nbformat is not installed for {sys.executable}.\n"
             "Run this with the project's environment: .venv/bin/python src/start.py")


def clear_outputs(path):
    """Remove outputs, run numbers and saved widget state from a notebook; returns how many outputs were removed."""
    nb = nbformat.read(path, as_version=4)
    removed = 0
    nb.metadata.pop("widgets", None)
    for cell in nb.cells:
        if cell.cell_type == "code":
            removed += len(cell.outputs)
            cell.outputs = []
            cell.execution_count = None
    nbformat.write(nb, path)
    return removed


def main(args):
    print(f"Cleared {clear_outputs(NOTEBOOK)} saved outputs from {NOTEBOOK.name}")
    if "--clear" in args:
        return 0
    cmd = [sys.executable, "-m", "jupyterlab", f"--config={CONFIG}", *args, str(NOTEBOOK)]
    try:
        return subprocess.run(cmd, cwd=ROOT).returncode
    except KeyboardInterrupt:  # Ctrl+C stops Jupyter; no traceback
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
