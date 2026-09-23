# MangFrag: Mangrove Fragmentation 1990–2024

This project takes yearly maps of mangrove forest and shows **how the forest has broken up over time**. For each year it:

1. **Labels every mangrove area** by how intact it is (see [the classes](#what-the-classes-mean) below).
2. **Measures fragmentation** with standard landscape-ecology numbers, such as number of patches, patch size and edge length.
3. **Saves the results** as ready-to-use maps, charts, Excel tables and GIS files.

You don't need any programming experience. Follow the steps below once, and after that you only need to double-click one file.

---

## Contents

- [What's in this folder](#whats-in-this-folder)
- [Step 1: Install Python (one time only)](#step-1-install-python-one-time-only)
- [Step 2: Start the project](#step-2-start-the-project)
- [Step 3: Run the analysis](#step-3-run-the-analysis)
- [Step 4: Find your results](#step-4-find-your-results)
- [Changing the settings](#changing-the-settings)
- [Using your own maps](#using-your-own-maps)
- [What the classes mean](#what-the-classes-mean)
- [Troubleshooting](#troubleshooting)
- [For advanced users](#for-advanced-users)

---

## What's in this folder

```
MangFrag/
├── start-windows.bat              ← Windows: double-click to start
├── start.command                  ← Mac: double-click to start
├── mangrove_fragmentation.ipynb   ← the analysis notebook (opens in your browser)
├── README.md                      ← this guide
├── data/
│   └── mangrove_1990-2024/        ← put the input maps here (not included)
├── outputs/                       ← YOUR RESULTS (created when you run the analysis)
├── src/                           ← program code (no need to open)
├── requirements.txt               ← list of required software (used automatically)
└── environment.yml                ← same list, for the alternative install
```

| File / folder | What it is |
|---|---|
| `start-windows.bat`, `start.command` | The only files you need to click. They install everything the first time, then open the notebook. |
| `mangrove_fragmentation.ipynb` | The analysis notebook. It opens in your web browser. |
| `data/` | Input maps. **They're not included with the project.** You get them separately and copy them here (see [Step 2](#step-2-start-the-project)). |
| `outputs/` | Created when you run the analysis. **This is where your results go.** |
| `src/` | `mangfrag.py` does the analysis, and `start.py` opens the notebook. You don't need to open them. |
| `requirements.txt`, `environment.yml` | Lists of required software. The start files read them automatically. |
| `.venv/` (hidden) | Created on first start. Holds the installed software. Don't edit it. |

---

## Step 1: Install Python (one time only)

The project needs **Python 3.12**. Python 3.13 also works. **3.14 and 3.11 do not.**

<details open>
<summary><b>Windows</b></summary>

1. Go to <https://www.python.org/downloads/windows/> and download the latest **Python 3.12** "Windows installer (64-bit)".
2. Open the downloaded file.
3. ⚠️ On the first screen, **tick "Add python.exe to PATH"** at the bottom.
4. Click **Install Now** and wait until it finishes.

</details>

<details open>
<summary><b>Mac</b></summary>

1. Go to <https://www.python.org/downloads/macos/> and download the latest **Python 3.12** "macOS 64-bit universal2 installer".
2. Open the downloaded `.pkg` file and click through the installer.
3. **Intel Mac?** (Apple menu → About This Mac says "Intel") The normal install won't work on Intel Macs. Skip to [Intel Mac](#intel-mac-or-when-the-normal-install-fails) instead.

</details>

<details>
<summary><b>Linux</b></summary>

Install Python 3.12 and venv with your package manager. On Ubuntu/Debian: `sudo apt install python3.12 python3.12-venv`.

</details>

---

## Step 2: Start the project

> 📂 **First, add the input maps.** The map files aren't included with the project. Copy the `.tif` files you received into **`data/mangrove_1990-2024/`**. Make that folder if it doesn't exist. See `data/README.md` for details.

| Computer | What to do |
|---|---|
| **Windows** | Double-click **`start-windows.bat`**. If a blue "Windows protected your PC" box appears, click **More info → Run anyway**. |
| **Mac** | Double-click **`start.command`**. If macOS says it "cannot be opened", **right-click** the file → **Open** → **Open**. You only need to do this once. |
| **Linux** | Open a terminal in this folder and run `bash start.command`. |

**The first time**, a black window appears and installs everything. This takes **5–10 minutes** and needs an internet connection. Later starts take a few seconds.

When it's ready, **the notebook opens in your web browser**.

> ⚠️ **Keep the black window open** while you work. Closing it stops the notebook. When you're done, close the browser tab and then the black window.

---

## Step 3: Run the analysis

In the browser:

1. In the top menu, click **Run → Run All Cells**.
2. Wait. Progress bars show each step. The full run takes about **2–5 minutes**.
3. Charts, tables and maps appear as you scroll down the page.

A notebook is a page made of blocks called "cells". Grey cells hold code, and the rest is explanation. You can read the explanations and look at the results without touching the code.

If a cell shows a red **⛔** message, an earlier cell hasn't run yet. Use **Run → Run All Cells** again.

The notebook always opens **empty**, without results from the last time. That's normal. Your saved results stay in the `outputs` folder.

---

## Step 4: Find your results

Everything is saved in the **`outputs`** folder, next to this file:

| Folder | Contents | Open with |
|---|---|---|
| `outputs/figures/` | Maps and charts (`.png`), high resolution for reports | Any image viewer, Word, PowerPoint |
| `outputs/tables/` | **`mangrove_fragmentation.xlsx`**: all numbers in one workbook, one sheet per table. The same tables are also saved as `.csv`. | Excel, LibreOffice, Google Sheets |
| `outputs/interactive/` | Zoomable map and flow diagrams (`.html`) | Double-click to open in a web browser |
| `outputs/rasters/` | Fragmentation map per year (`.tif`) | QGIS, ArcGIS |

The Excel workbook includes a `metric_definitions` sheet that explains every measurement, and a `parameters` sheet that records the settings used.

Running the analysis again **overwrites** the files in `outputs/`. To keep a previous run, rename the folder first, e.g. to `outputs_run1`.

---

## Changing the settings

The first grey cell of the notebook holds the settings. Change a number, then **Run → Run All Cells**.

| Setting | Default | Meaning |
|---|---|---|
| `EDGE_WIDTH_M` | `100` | How far (in meters) the forest edge reaches into the forest. Mangrove closer than this to open land counts as "edge". |
| `GAP_MAX_HA` | `5` | Openings inside the forest smaller than this (hectares) count as small holes ("perforated"). Larger openings count as outer boundary ("edge"). |
| `CORE_SMALL_HA` | `100` | Core areas smaller than this (ha) are "small core". |
| `CORE_LARGE_HA` | `200` | Core areas this size or bigger (ha) are "large core". Sizes in between are "medium core". |
| `ENN` | `True` | Also computes the distance between patches. Set it to `False` for a faster run without this measurement. |

---

## Using your own maps

1. Make a new folder inside `data/`, for example `data/my_maps/`, and put your maps in it.
2. In the settings cell, change `DATA_DIR = Path("data/mangrove_1990-2024")` to `DATA_DIR = Path("data/my_maps")`.

Each map must:

- be a GeoTIFF (`.tif`), with **one file per year**
- have the **year in the file name**, e.g. `classification_2020.tif`
- use pixel value **1 = mangrove** and **0 = not mangrove**
- cover the same area with the same pixel grid as the other years

---

## What the classes mean

Each mangrove pixel is placed in one class. The method follows the Landscape Fragmentation Tool (Vogt et al. 2007; Parent & Hurd, LFT v2).

| Class | Meaning |
|---|---|
| 🟥 **Patch** | Small or thin pieces of mangrove, too small to have any interior (core) |
| 🟧 **Edge** | Mangrove along the outer border with open land or water |
| 🟪 **Perforated** | Mangrove around small holes inside the forest |
| 🟩 **Small core** | Interior forest, far from any edge, in blocks under 100 ha |
| 🟩 **Medium core** | Interior forest in blocks of 100–200 ha |
| 🟩 **Large core** | Interior forest in blocks over 200 ha. This is the most intact forest. |

A **healthy, intact** forest has mostly large core. **Increasing fragmentation** shows up as core shrinking while patch, edge and perforated areas grow.

---

## Troubleshooting

**"Python 3.12 was not found"**
Install Python as described in [Step 1](#step-1-install-python-one-time-only). On Windows, make sure "Add python.exe to PATH" was ticked. If it wasn't, run the installer again, choose **Modify**, and tick it. Then restart the computer.

**"Installation failed"**
- Check your internet connection and try again. The start file automatically retries the setup.
- Check you installed Python **3.12** or **3.13**, not 3.14.
- Still failing? Use [the alternative install](#intel-mac-or-when-the-normal-install-fails) below.

**The browser didn't open**
Look in the black window for a line starting with `http://localhost:8888/lab?token=...`. Copy the whole line into your browser.

**"Port 8888 is already in use"** or a second notebook opens
The notebook is already running in another black window. Use that one, or close it and start again.

**"no .tif files in data/mangrove_1990-2024"**
The input maps are missing. Copy them into that folder (see [Step 2](#step-2-start-the-project)), or point `DATA_DIR` at the folder where your maps are.

**Something is broken and you want a clean start**
Close everything, delete the **`.venv`** folder, then double-click the start file again. It reinstalls from scratch.

### Intel Mac, or when the normal install fails

One of the required tools (`pylandstats`) has no ready-made installer for Intel Macs or for Windows on ARM. Use **Miniforge** instead, which works on all computers:

1. Download and install Miniforge from <https://conda-forge.org/download/>.
2. Open **Miniforge Prompt** (Windows) or **Terminal** (Mac/Linux).
3. Type `cd ` (with a space), drag this project folder into the window, and press Enter.
4. Run these lines one at a time. The first one takes 5–10 minutes.
   ```
   conda env create -f environment.yml
   conda activate mangfrag
   python src/start.py
   ```
5. Next time, just repeat steps 2–3, then run the last two lines.

---

## For advanced users

```bash
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/start.py                  # open the notebook (clears its saved outputs first)

python src/mangfrag.py --check       # quick self-test of the segmentation
python src/mangfrag.py               # run everything without the notebook, write outputs/
```

The landscape metrics are computed with `pylandstats` and named like the R package `landscapemetrics` (`lsm_c_ca`, `lsm_c_np`, `lsm_c_ed`, …). They use the same conventions: 8-neighbour patches, landscape boundary not counted as edge, area in ha, edge density in m/ha, and patch density per 100 ha.

**Sharing this project:** send the folder **without** `.venv/`, `outputs/` and the map files in `data/`. Share the maps separately. `.venv` only works on the computer that created it, and the start file rebuilds it on each new computer. The `.gitignore` excludes all three when you use Git. Only `data/README.md` is kept.
