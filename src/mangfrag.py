"""Mangrove fragmentation segmentation + landscape metrics, 1990-2024.

Segmentation follows the Landscape Fragmentation Tool (Vogt et al. 2007 /
Parent & Hurd, LFT v2): every mangrove pixel is Patch, Edge, Perforated or
Core (small / medium / large). Landscape metrics come from pylandstats and
are renamed to the R `landscapemetrics` names (lsm_c_*), with the same
conventions: 8-neighbour patches, landscape boundary not counted as edge,
area in ha, ED in m/ha, PD per 100 ha.

    python src/mangfrag.py           # full analysis, everything written to outputs/
    python src/mangfrag.py --check   # synthetic self-check of the segmentation
"""
from pathlib import Path
from types import SimpleNamespace
import base64
import io
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import rasterio
import pylandstats as pls
from scipy import ndimage as ndi
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import plotly.graph_objects as go
from PIL import Image
from tqdm.auto import tqdm  # widget bar in Jupyter, text bar in a terminal

ROOT = Path(__file__).resolve().parent.parent  # project folder (this file is in src/)
DATA_DIR = ROOT / "data" / "mangrove_1990-2024"
OUT_DIR = ROOT / "outputs"
MANGROVE = 1          # class value of mangrove in the input rasters
NODATA = 255          # rasters have no nodata; 0 = non-mangrove is a real class

# Tunables (LFT defaults converted to metric)
EDGE_WIDTH_M = 100                   # edge depth; pixels closer than this to non-mangrove are not core
GAP_MAX_HA = 5                       # enclosed non-mangrove openings smaller than this are perforations
CORE_SMALL_HA, CORE_LARGE_HA = 100, 200  # ~LFT 250 / 500 acres

CLASSES = {  # value: (label, colour)
    0: ("Non-mangrove", "#e6e5e0"),
    1: ("Patch", "#e34948"),
    2: ("Edge", "#eda100"),
    3: ("Perforated", "#4a3aa7"),
    4: ("Small core", "#4caf5c"),
    5: ("Medium core", "#1f7a33"),
    6: ("Large core", "#0b4a1a"),
}
LABELS = [v[0] for v in CLASSES.values()]
COLORS = [v[1] for v in CLASSES.values()]
EIGHT = np.ones((3, 3), bool)

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 300, "savefig.bbox": "tight",
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#8a8984", "axes.labelcolor": "#52514e",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.grid": True, "axes.axisbelow": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.6,
})


# ---------------------------------------------------------------- data

def load_years(data_dir=DATA_DIR):
    """{year: bool mangrove mask}, rasterio profile (all rasters must share a grid)."""
    masks, profile = {}, None
    for f in tqdm(sorted(Path(data_dir).glob("*.tif")), desc="Loading rasters", unit="file"):
        year = int(re.search(r"(?:19|20)\d{2}", f.name).group())
        with rasterio.open(f) as src:
            if profile and (src.shape, src.transform) != ((profile["height"], profile["width"]), profile["transform"]):
                raise ValueError(f"{f.name} is not on the same grid as the other years")
            masks[year] = src.read(1) == MANGROVE
            profile = src.profile
    if not masks:
        raise FileNotFoundError(f"no .tif files in {data_dir}")
    return dict(sorted(masks.items())), profile


def pixel_size_m(profile):
    """(height, width) of one pixel in metres; geographic CRS converted at the scene's centre latitude."""
    t = profile["transform"]
    if profile["crs"].is_geographic:
        lat = np.radians(t.f + t.e * profile["height"] / 2)
        return abs(t.e) * 110574.0, t.a * 111320.0 * np.cos(lat)
    return abs(t.e), t.a


def extent(profile):
    """(left, right, bottom, top) for imshow."""
    t = profile["transform"]
    return t.c, t.c + t.a * profile["width"], t.f + t.e * profile["height"], t.f


# ---------------------------------------------------------------- segmentation

def segment(mask, py, px):
    """LFT fragmentation classes (see CLASSES) for a bool mangrove mask."""
    pix_ha = py * px / 1e4
    # distance of each mangrove pixel to the nearest non-mangrove pixel, and where that pixel is
    dist, (iy, ix) = ndi.distance_transform_edt(mask, sampling=(py, px), return_indices=True)
    core = mask & (dist > EDGE_WIDTH_M)

    patches, n = ndi.label(mask, EIGHT)
    has_core = np.zeros(n + 1, bool)
    has_core[np.unique(patches[core])] = True
    has_core[0] = False

    # small non-mangrove openings fully enclosed by mangrove = perforations
    gaps, ng = ndi.label(~mask)  # 4-connectivity: the complement of 8-connected patches
    small_gap = np.bincount(gaps.ravel(), minlength=ng + 1) * pix_ha < GAP_MAX_HA
    small_gap[np.unique(np.r_[gaps[0], gaps[-1], gaps[:, 0], gaps[:, -1]])] = False
    small_gap[0] = False
    near_gap = small_gap[gaps[iy, ix]]

    seg = np.zeros(mask.shape, np.uint8)
    seg[mask & ~has_core[patches]] = 1
    fringe = mask & ~core & has_core[patches]
    seg[fringe & ~near_gap] = 2
    seg[fringe & near_gap] = 3

    cores, nc = ndi.label(core, EIGHT)
    core_ha = np.bincount(cores.ravel(), minlength=nc + 1) * pix_ha
    size_cls = np.select([core_ha < CORE_SMALL_HA, core_ha < CORE_LARGE_HA], [4, 5], 6).astype(np.uint8)
    seg[core] = size_cls[cores[core]]
    return seg


# ---------------------------------------------------------------- metrics

def _aggregation_index(mask):
    """lsm_c_ai: like adjacencies (single count, 4-neighbour) / maximum possible for that area."""
    g = np.count_nonzero(mask[:, 1:] & mask[:, :-1]) + np.count_nonzero(mask[1:] & mask[:-1])
    a = int(mask.sum())
    n = int(np.sqrt(a)); m = a - n * n
    gmax = 2 * n * (n - 1) + (0 if m == 0 else 2 * m - 1 if m <= n else 2 * m - 2)
    return 100 * g / gmax if gmax else np.nan


def landscape_metrics(mask, py, px, edge_width_m=EDGE_WIDTH_M, enn=True):
    """Class-level metrics for mangrove (landscapemetrics names) + per-patch table."""
    arr = mask.astype(np.uint8)
    ls = pls.Landscape(arr, res=(px, py), nodata=NODATA)
    edge_depth = max(1, round(edge_width_m / ((px + py) / 2)))  # cells, as lsm_c_tca(edge_depth=)
    c = dict(class_val=1)
    patches = ls.compute_patch_metrics_df(metrics=["area", "perimeter", "shape_index", "fractal_dimension"])
    patches = patches[patches["class_val"] == 1]
    a = patches["area"].to_numpy()
    A = mask.size * py * px / 1e4  # landscape area, ha (pylandstats reports m2)
    row = {
        "ca": ls.total_area(**c),
        "pland": ls.proportion_of_landscape(**c),
        "np": ls.number_of_patches(**c),
        "pd": ls.patch_density(**c),
        "lpi": ls.largest_patch_index(**c),
        "te": ls.total_edge(**c, count_boundary=False),
        "ed": ls.edge_density(**c, count_boundary=False),
        "lsi": ls.landscape_shape_index(**c),
        "area_mn": a.mean(), "area_md": np.median(a), "area_sd": a.std(ddof=1), "area_am": (a * a).sum() / a.sum(),
        "shape_mn": patches["shape_index"].mean(),
        "frac_mn": patches["fractal_dimension"].mean(),
        "ndca": ls.number_of_disjunct_core_areas(**c, edge_depth=edge_depth, count_boundary=False),
        "mesh": (a * a).sum() / A,
        "division": 1 - ((a / A) ** 2).sum(),
        "split": A * A / (a * a).sum(),
        "ai": _aggregation_index(mask),
    }
    row["core_mn"] = ls.core_area_mn(**c, edge_depth=edge_depth, count_boundary=False)
    row["tca"] = row["core_mn"] * row["np"]
    row["cpland"] = 100 * row["tca"] / A
    if enn:  # ponytail: ~35 s/year on this scene; pass enn=False while iterating
        row["enn_mn"] = ls.euclidean_nearest_neighbor_mn(**c)
    return row, patches[["area", "perimeter", "shape_index", "fractal_dimension"]].reset_index(drop=True)


METRIC_INFO = {  # name: (description, unit)
    "ca": ("Total class area", "ha"), "pland": ("Percentage of landscape", "%"),
    "np": ("Number of patches", "n"), "pd": ("Patch density", "n / 100 ha"),
    "lpi": ("Largest patch index", "%"), "te": ("Total edge", "m"), "ed": ("Edge density", "m / ha"),
    "lsi": ("Landscape shape index", "-"), "area_mn": ("Mean patch area", "ha"),
    "area_md": ("Median patch area", "ha"), "area_sd": ("SD patch area", "ha"),
    "area_am": ("Area-weighted mean patch area", "ha"), "shape_mn": ("Mean shape index", "-"),
    "frac_mn": ("Mean fractal dimension", "-"), "tca": ("Total core area", "ha"),
    "ndca": ("Number of disjunct core areas", "n"), "core_mn": ("Mean core area per patch", "ha"),
    "cpland": ("Core area % of landscape", "%"), "mesh": ("Effective mesh size", "ha"),
    "division": ("Landscape division index", "0-1"), "split": ("Splitting index", "-"),
    "ai": ("Aggregation index", "%"), "enn_mn": ("Mean nearest-neighbour distance", "m"),
}


def composition(segs, pix_ha):
    """Area (ha) of each fragmentation class per year."""
    rows = {y: np.bincount(s.ravel(), minlength=len(CLASSES)) * pix_ha for y, s in segs.items()}
    return pd.DataFrame.from_dict(rows, orient="index", columns=LABELS).rename_axis("year")


def transitions(seg_a, seg_b, pix_ha):
    """Class-to-class transition matrix (ha); rows = from, columns = to."""
    k = len(CLASSES)
    m = np.bincount(seg_a.ravel().astype(np.int64) * k + seg_b.ravel(), minlength=k * k).reshape(k, k)
    return pd.DataFrame(m * pix_ha, index=pd.Index(LABELS, name="from"), columns=pd.Index(LABELS, name="to"))


def change_map(mask_a, mask_b):
    """0 never mangrove, 1 loss, 2 gain, 3 stable mangrove."""
    return (mask_a & ~mask_b) * 1 + (~mask_a & mask_b) * 2 + (mask_a & mask_b) * 3


def load(data_dir=DATA_DIR):
    """Read every year's raster; returns the results namespace the later steps fill in."""
    masks, profile = load_years(data_dir)
    py, px = pixel_size_m(profile)
    return SimpleNamespace(masks=masks, profile=profile, py=py, px=px, pix_ha=py * px / 1e4,
                           years=list(masks), extent=extent(profile), data_dir=Path(data_dir).resolve())


def run_segmentation(res, edge_width_m=None, gap_max_ha=None, core_small_ha=None, core_large_ha=None):
    """Segment every year. Parameters left as None keep the module defaults; the values used are
    recorded in res.seg_params so later steps can tell whether results are stale."""
    global EDGE_WIDTH_M, GAP_MAX_HA, CORE_SMALL_HA, CORE_LARGE_HA
    EDGE_WIDTH_M = EDGE_WIDTH_M if edge_width_m is None else edge_width_m
    GAP_MAX_HA = GAP_MAX_HA if gap_max_ha is None else gap_max_ha
    CORE_SMALL_HA = CORE_SMALL_HA if core_small_ha is None else core_small_ha
    CORE_LARGE_HA = CORE_LARGE_HA if core_large_ha is None else core_large_ha
    res.seg_params = dict(edge_width_m=EDGE_WIDTH_M, gap_max_ha=GAP_MAX_HA,
                          core_small_ha=CORE_SMALL_HA, core_large_ha=CORE_LARGE_HA)
    res.segs = {y: segment(m, res.py, res.px)
                for y, m in tqdm(res.masks.items(), total=len(res.masks), desc="Segmentation", unit="year")}
    res.composition = composition(res.segs, res.pix_ha)
    return res


def run_metrics(res, enn=True):
    edge_width_m = res.seg_params["edge_width_m"]
    rows, patch_tables = {}, {}
    # one process per year; tunables passed explicitly because workers re-import this module
    with ProcessPoolExecutor() as ex:
        jobs = {ex.submit(landscape_metrics, m, res.py, res.px, edge_width_m, enn): y for y, m in res.masks.items()}
        for job in tqdm(as_completed(jobs), total=len(jobs), desc="Landscape metrics", unit="year"):
            y = jobs[job]
            rows[y], p = job.result()
            patch_tables[y] = p.assign(year=y)
    res.metrics = pd.DataFrame.from_dict(rows, orient="index").sort_index().rename_axis("year")
    res.patches = pd.concat([patch_tables[y] for y in sorted(patch_tables)], ignore_index=True)
    res.metric_params = dict(**res.seg_params, enn=enn)
    return res


def analyze(data_dir=DATA_DIR, enn=True):
    return run_metrics(run_segmentation(load(data_dir)), enn)


# ---------------------------------------------------------------- figures

def _cmap():
    return ListedColormap(COLORS)


def _legend(ax_or_fig, classes=CLASSES, **kw):
    handles = [Patch(facecolor=c, edgecolor="#8a8984", linewidth=0.4, label=l) for l, c in classes.values()]
    return ax_or_fig.legend(handles=handles, frameon=False, **kw)


def _map_furniture(ax, ext, km=10):
    """Scale bar (bottom-left) and north arrow (top-right) on a lon/lat axis."""
    left, right, bottom, top = ext
    lat = np.radians((bottom + top) / 2)
    deg = km * 1000 / (111320 * np.cos(lat))
    x0, y0 = left + (right - left) * 0.05, bottom + (top - bottom) * 0.05
    ax.plot([x0, x0 + deg], [y0, y0], color="#0b0b0b", lw=3, solid_capstyle="butt")
    ax.text(x0 + deg / 2, y0 + (top - bottom) * 0.015, f"{km} km", ha="center", va="bottom", fontsize=8)
    ax.annotate("N", xy=(0.94, 0.95), xytext=(0.94, 0.85), xycoords="axes fraction",
                ha="center", va="center", fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="#0b0b0b", lw=1.5))


def plot_map(seg, year, ext, ax=None):
    """One detailed fragmentation map."""
    fig, ax = (ax.figure, ax) if ax else plt.subplots(figsize=(8, 9))
    ax.imshow(seg, cmap=_cmap(), vmin=0, vmax=len(CLASSES) - 1, extent=ext, interpolation="nearest")
    ax.set(title=f"Mangrove fragmentation {year}", xlabel="Longitude (°E)", ylabel="Latitude (°)")
    ax.grid(False)
    _map_furniture(ax, ext)
    _legend(ax, loc="upper left", bbox_to_anchor=(1.01, 1))
    return fig


def plot_map_grid(segs, ext, ncols=4):
    """Small multiples: one map per year, shared legend."""
    n = len(segs); nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.4 * ncols, 4 * nrows), sharex=True, sharey=True)
    for ax, (y, s) in zip(axes.flat, segs.items()):
        ax.imshow(s, cmap=_cmap(), vmin=0, vmax=len(CLASSES) - 1, extent=ext, interpolation="nearest")
        ax.set_title(str(y)); ax.grid(False); ax.tick_params(labelsize=7)
    for ax in axes.flat[n:]:
        ax.remove()
    _legend(fig, loc="lower center", ncol=len(CLASSES), bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Mangrove fragmentation classes, 1990-2024", fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    return fig


def plot_composition(comp, percent=False):
    """Stacked bars of mangrove area by fragmentation class (non-mangrove excluded)."""
    d = comp.drop(columns="Non-mangrove")
    if percent:
        d = d.div(d.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(d)); bottom = np.zeros(len(d))
    for label in d.columns:
        color = COLORS[LABELS.index(label)]
        ax.bar(x, d[label], 0.62, bottom=bottom, color=color, edgecolor="white", linewidth=1.5, label=label)
        bottom += d[label].to_numpy()
    for xi, total in zip(x, bottom):
        ax.text(xi, total, f"{total:,.0f}" if not percent else "", ha="center", va="bottom", fontsize=8, color="#52514e")
    ax.set_xticks(x, d.index)
    ax.set_ylabel("Share of mangrove area (%)" if percent else "Area (ha)")
    ax.set_title("Mangrove area by fragmentation class" + (" (%)" if percent else ""))
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1))
    return fig


def plot_metrics(metrics, names=("ca", "np", "pd", "lpi", "ed", "area_mn", "mesh", "tca", "ndca", "shape_mn", "ai", "enn_mn")):
    """Small multiples, one line per metric (each on its own axis - never dual-axis)."""
    names = [n for n in names if n in metrics]
    ncols = 4; nrows = -(-len(names) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 3 * nrows), sharex=True)
    for ax, n in zip(axes.flat, names):
        desc, unit = METRIC_INFO[n]
        ax.plot(metrics.index, metrics[n], color="#2a78d6", lw=2, marker="o", ms=5,
                markeredgecolor="white", markeredgewidth=1)
        ax.set_title(f"{n.upper()} · {desc}", fontsize=8.5, loc="left")
        ax.set_ylabel(unit, fontsize=8)
        first, last = metrics[n].iloc[0], metrics[n].iloc[-1]
        value = f"{last:,.0f}" if abs(last) >= 100 else f"{last:.3g}"
        change = f"  ({(last - first) / abs(first) * 100:+.0f}% vs {metrics.index[0]})" if first else ""
        ax.set_xlabel(f"{metrics.index[-1]}: {value}{change}", fontsize=8, loc="right")
    for ax in axes.flat[len(names):]:
        ax.remove()
    fig.suptitle("Landscape metrics - mangrove class (landscapemetrics names)", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_patch_sizes(patches):
    """Distribution of patch areas per year (log scale)."""
    years = sorted(patches["year"].unique())
    data = [patches.loc[patches.year == y, "area"] for y in years]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.boxplot(data, tick_labels=[str(y) for y in years], showfliers=True, widths=0.5,
               boxprops=dict(color="#2a78d6"), medianprops=dict(color="#0b0b0b", lw=1.5),
               whiskerprops=dict(color="#8a8984"), capprops=dict(color="#8a8984"),
               flierprops=dict(marker=".", markersize=3, markerfacecolor="#86b6ef", markeredgecolor="none"))
    ax.set_yscale("log")
    ax.set(ylabel="Patch area (ha, log scale)", title="Mangrove patch size distribution")
    ax.grid(axis="x", visible=False)
    return fig


CHANGE_CLASSES = {0: ("Never mangrove", "#ffffff"), 1: ("Loss", "#e34948"), 2: ("Gain", "#2a78d6"), 3: ("Stable mangrove", "#b5b4ae")}


def plot_change(mask_a, mask_b, ya, yb, ext, pix_ha):
    ch = change_map(mask_a, mask_b)
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.imshow(ch, cmap=ListedColormap([c for _, c in CHANGE_CLASSES.values()]), vmin=0, vmax=3,
              extent=ext, interpolation="nearest")
    area = np.bincount(ch.ravel(), minlength=4) * pix_ha
    ax.set(title=f"Mangrove change {ya} → {yb}   loss {area[1]:,.0f} ha · gain {area[2]:,.0f} ha",
           xlabel="Longitude (°E)", ylabel="Latitude (°)")
    ax.grid(False)
    _map_furniture(ax, ext)
    _legend(ax, classes={k: v for k, v in CHANGE_CLASSES.items() if k}, loc="upper left", bbox_to_anchor=(1.01, 1))
    return fig


def sankey(segs, years, pix_ha):
    """Plotly Sankey of fragmentation-class flows across the given years.

    Every year is measured over the same domain - pixels that are mangrove in at least one of
    `years` - so each column sums to the same area. Nodes are placed explicitly (evenly spaced
    columns, same class order every year) so the diagram keeps one height from start to end.
    """
    k = len(CLASSES)
    order = [6, 5, 4, 3, 2, 1, 0]  # top -> bottom: cores, perforated, edge, patch, non-mangrove
    gap = 0.015                    # vertical gap between nodes, fraction of plot height
    domain = np.logical_or.reduce([segs[y] > 0 for y in years])
    total = domain.sum() * pix_ha
    area = {y: np.bincount(segs[y][domain], minlength=k) * pix_ha for y in years}

    node, label, full, color, xs, ys = {}, [], [], [], [], []
    for i, y in enumerate(years):
        present = [c for c in order if area[y][c] > 0]
        scale = (1 - gap * (len(order) - 1)) / total  # same scale for every column
        top = 0.0
        for c in present:
            h = area[y][c] * scale
            node[i, c] = len(label)
            label.append(LABELS[c]); full.append(f"{LABELS[c]} {y}"); color.append(COLORS[c])
            xs.append(0.001 + 0.998 * i / (len(years) - 1))
            ys.append(min(max(top + h / 2, 0.001), 0.999))
            top += h + gap

    src, dst, val, col = [], [], [], []
    for i, (ya, yb) in enumerate(zip(years, years[1:])):
        t = transitions(segs[ya][domain], segs[yb][domain], pix_ha).to_numpy()
        for a, b in zip(*np.nonzero(t)):
            src.append(node[i, a]); dst.append(node[i + 1, b]); val.append(t[a, b])
            col.append(_rgba(COLORS[a], 0.45))
    link_text = [f"{full[a]} → {full[b]}" for a, b in zip(src, dst)]

    fig = go.Figure(go.Sankey(
        arrangement="fixed",
        node=dict(label=label, customdata=full, color=color, x=xs, y=ys, pad=6, thickness=14, line=dict(width=0),
                  hovertemplate="%{customdata}<br>%{value:,.0f} ha<extra></extra>"),
        link=dict(source=src, target=dst, value=val, color=col, customdata=link_text,
                  hovertemplate="%{customdata}<br>%{value:,.1f} ha<extra></extra>"),
        valueformat=",.0f", valuesuffix=" ha"))
    span = f"{years[0]} → {years[1]}" if len(years) == 2 else f"{years[0]}–{years[-1]} ({len(years)} dates)"
    fig.update_layout(title=f"Fragmentation class transitions {span}"
                            f"<br><sup>Area that was mangrove in at least one year: {total:,.0f} ha</sup>",
                      font=dict(size=11), height=720, margin=dict(l=20, r=20, t=100, b=20))
    for i, y in enumerate(years):  # one year heading per column instead of the year in every node label
        fig.add_annotation(x=0.001 + 0.998 * i / (len(years) - 1), y=1.02, xref="paper", yref="paper",
                           text=f"<b>{y}</b>", showarrow=False, yanchor="bottom",
                           xanchor="left" if i == 0 else "right" if i == len(years) - 1 else "center")
    return fig


def _rgba(hex_, alpha):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _to_rgba(arr, classes):
    lut = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] + [0 if k == 0 else 255]
                    for k, (_, c) in classes.items()], np.uint8)
    return lut[arr]


def _png_data_uri(rgba):
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


MAPLIBRE = "https://cdn.jsdelivr.net/npm/maplibre-gl@5/dist/maplibre-gl"

_MAP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mangrove fragmentation map</title>
<link rel="stylesheet" href="__MAPLIBRE__.css">
<script src="__MAPLIBRE__.js"></script>
<style>
  html, body, #map { margin: 0; height: 100%; }
  body { font: 13px/1.4 system-ui, sans-serif; color: #0b0b0b; }
  .panel { position: absolute; top: 10px; left: 10px; z-index: 2; background: #fff; border-radius: 8px;
           padding: 10px 12px; box-shadow: 0 1px 6px rgba(0,0,0,.25); max-width: 230px; }
  .panel h3 { margin: 0 0 6px; font-size: 13px; }
  .panel section + section { margin-top: 10px; border-top: 1px solid #e6e5e0; padding-top: 8px; }
  .panel { max-height: calc(100% - 40px); overflow-y: auto; width: 250px; max-width: none; box-sizing: border-box; }
  .row { display: grid; grid-template-columns: auto 1fr 34px; align-items: center; gap: 8px; margin: 3px 0; }
  .row button { border: 1px solid #b5b4ae; background: #fff; border-radius: 4px; padding: 3px 7px; cursor: pointer;
                font: inherit; min-width: 48px; }
  .row button.on { background: #0b4a1a; border-color: #0b4a1a; color: #fff; }
  #change-row button.on { background: #2a78d6; border-color: #2a78d6; }
  .row input[type=range] { width: 100%; margin: 0; }
  .row input[type=range]:disabled { opacity: .35; }
  .row .val { font-size: 11px; color: #52514e; text-align: right; font-variant-numeric: tabular-nums; }
  label { display: block; cursor: pointer; }
  .sw { display: inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; border: 1px solid #8a8984; }
  .hint { margin-top: 6px; color: #52514e; font-size: 12px; }
  .hint a { color: #2a78d6; }
</style></head>
<body><div id="map"></div>
<div class="panel">
  <section><h3>Fragmentation year · opacity</h3><div id="years"></div>
    <div class="hint">Several years can be on (later years draw on top).
      <a href="#" id="all">All</a> · <a href="#" id="none">None</a></div></section>
  <section><h3>Change layer · opacity</h3><div id="change-row"></div>
    <div class="hint">Turning it on hides the years, and vice versa.</div></section>
  <section><h3>Basemap</h3>
    <label><input type="radio" name="base" value="sat" checked> Satellite</label>
    <label><input type="radio" name="base" value="osm"> OpenStreetMap</label></section>
  <section><h3>Legend</h3><div id="legend"></div></section>
</div>
<script>
const LAYERS = __LAYERS__;          // [{id, label, url}]
const CHANGE = __CHANGE__;          // {id, url}
const LEGEND = __LEGEND__;          // [[label, colour]]
const CORNERS = __CORNERS__;        // TL, TR, BR, BL as [lon, lat]
const BOUNDS = __BOUNDS__;

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      sat: { type: "raster", tileSize: 256, attribution: "Esri World Imagery",
             tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"] },
      osm: { type: "raster", tileSize: 256, attribution: "© OpenStreetMap contributors",
             tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"] }
    },
    layers: [
      { id: "sat", type: "raster", source: "sat" },
      { id: "osm", type: "raster", source: "osm", layout: { visibility: "none" } }
    ]
  },
  bounds: BOUNDS, fitBoundsOptions: { padding: 20 }
});
map.addControl(new maplibregl.NavigationControl(), "top-right");
// fullscreen the whole page, not just the map, so the filter panel stays visible
map.addControl(new maplibregl.FullscreenControl({ container: document.documentElement }), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

const OPACITY = 0.9;
const rows = {};  // layer id -> {button, slider}

// one row per layer: on/off button + its own opacity slider
function addRow(parent, l, visible, onToggle) {
  map.addSource(l.id, { type: "image", url: l.url, coordinates: CORNERS });
  map.addLayer({ id: l.id, type: "raster", source: l.id,
                 layout: { visibility: visible ? "visible" : "none" },
                 paint: { "raster-resampling": "nearest", "raster-fade-duration": 0, "raster-opacity": OPACITY } });
  const row = document.createElement("div");
  row.className = "row";
  row.innerHTML = `<button type="button">${l.label}</button>
    <input type="range" min="0" max="1" step="0.05" value="${OPACITY}" aria-label="${l.label} opacity">
    <span class="val">${Math.round(OPACITY * 100)}%</span>`;
  const [button, slider, val] = row.children;
  button.onclick = () => onToggle(!button.classList.contains("on"));
  slider.oninput = () => {
    map.setPaintProperty(l.id, "raster-opacity", +slider.value);
    val.textContent = `${Math.round(slider.value * 100)}%`;
  };
  parent.appendChild(row);
  rows[l.id] = { button, slider };
  setOn(l.id, visible);
}
function setOn(id, on) {
  map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  rows[id].button.classList.toggle("on", on);
  rows[id].slider.disabled = !on;
}
const setYears = on => LAYERS.forEach(l => setOn(l.id, on));

map.once("style.load", () => {  // style ready: add overlays without waiting for basemap tiles
  const years = document.getElementById("years");
  LAYERS.forEach((l, i) => addRow(years, l, i === LAYERS.length - 1, on => {
    setOn(l.id, on);
    if (on) setOn(CHANGE.id, false);   // a year on -> change layer off
  }));
  addRow(document.getElementById("change-row"), CHANGE, false, on => {
    setOn(CHANGE.id, on);
    if (on) setYears(false);           // change layer on -> all years off
  });
  document.getElementById("all").onclick = e => { e.preventDefault(); setYears(true); setOn(CHANGE.id, false); };
  document.getElementById("none").onclick = e => { e.preventDefault(); setYears(false); };
  document.querySelectorAll("input[name=base]").forEach(r => r.onchange = () =>
    ["sat", "osm"].forEach(id => map.setLayoutProperty(id, "visibility", id === r.value ? "visible" : "none")));
});
document.getElementById("legend").innerHTML = LEGEND
  .map(([l, c]) => `<div><span class="sw" style="background:${c}"></span>${l}</div>`).join("");
</script></body></html>
"""


def web_map(res):
    """Self-contained MapLibre GL page: one toggleable layer per year + first→last change layer over
    satellite / OSM basemaps. Layers are embedded as PNG data URIs so the file also works from disk."""
    left, right, bottom, top = res.extent
    y0, y1 = res.years[0], res.years[-1]
    layers = [{"id": f"frag{y}", "label": str(y), "url": _png_data_uri(_to_rgba(s, CLASSES))}
              for y, s in res.segs.items()]
    change = {"id": "change", "label": f"{y0} → {y1}", "url": _png_data_uri(_to_rgba(change_map(res.masks[y0], res.masks[y1]), CHANGE_CLASSES))}
    legend = list(CLASSES.values())[1:] + list(CHANGE_CLASSES.values())[1:]
    fill = {
        "__MAPLIBRE__": MAPLIBRE, "__Y0__": str(y0), "__Y1__": str(y1),
        "__LAYERS__": json.dumps(layers), "__CHANGE__": json.dumps(change), "__LEGEND__": json.dumps(legend),
        "__CORNERS__": json.dumps([[left, top], [right, top], [right, bottom], [left, bottom]]),
        "__BOUNDS__": json.dumps([[left, bottom], [right, top]]),
    }
    html = _MAP_HTML
    for k, v in fill.items():
        html = html.replace(k, v)
    return html


# ---------------------------------------------------------------- export

def write_geotiff(arr, profile, path, classes=CLASSES):
    p = {**profile, "dtype": "uint8", "count": 1, "nodata": None, "compress": "lzw"}
    with rasterio.open(path, "w", **p) as dst:
        dst.write(arr.astype(np.uint8), 1)
        dst.write_colormap(1, {k: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,) for k, (_, c) in classes.items()})


def save_figure(fig, name, out_dir=OUT_DIR):
    """Write a figure to <out_dir>/figures/<name>.png, close it, return the path."""
    path = Path(out_dir) / "figures" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def save_figures(figs, out_dir=OUT_DIR, desc="Figures"):
    """{name: callable returning a figure} -> saved PNG paths, with a render/save progress bar."""
    paths = []
    with tqdm(total=2 * len(figs), desc=desc, unit="step") as bar:
        for name, make in figs.items():
            bar.set_postfix_str(f"render {name}")
            fig = make()
            bar.update()
            bar.set_postfix_str(f"save {name}")
            paths.append(save_figure(fig, name, out_dir))
            bar.update()
        bar.set_postfix_str("done")
    return paths


def export_figures(res, out_dir=OUT_DIR):
    y0, y1 = res.years[0], res.years[-1]
    figs = {  # built lazily so the progress bar tracks each one
        "maps_all_years": lambda: plot_map_grid(res.segs, res.extent),
        f"map_{y0}": lambda: plot_map(res.segs[y0], y0, res.extent),
        f"map_{y1}": lambda: plot_map(res.segs[y1], y1, res.extent),
        "composition_ha": lambda: plot_composition(res.composition),
        "composition_pct": lambda: plot_composition(res.composition, percent=True),
        "landscape_metrics": lambda: plot_metrics(res.metrics),
        "patch_sizes": lambda: plot_patch_sizes(res.patches),
        f"change_{y0}_{y1}": lambda: plot_change(res.masks[y0], res.masks[y1], y0, y1, res.extent, res.pix_ha),
    }
    return save_figures(figs, out_dir)


def export_rasters(res, out_dir=OUT_DIR):
    d = Path(out_dir) / "rasters"
    d.mkdir(parents=True, exist_ok=True)
    y0, y1 = res.years[0], res.years[-1]
    for y, s in tqdm(res.segs.items(), desc="GeoTIFFs", unit="year"):
        write_geotiff(s, res.profile, d / f"fragmentation_{y}.tif")
    write_geotiff(change_map(res.masks[y0], res.masks[y1]), res.profile, d / f"change_{y0}_{y1}.tif", CHANGE_CLASSES)
    return d


def export_tables(res, out_dir=OUT_DIR):
    d = Path(out_dir) / "tables"
    d.mkdir(parents=True, exist_ok=True)
    y0, y1 = res.years[0], res.years[-1]
    comp_pct = res.composition.drop(columns="Non-mangrove")
    comp_pct = comp_pct.div(comp_pct.sum(axis=1), axis=0) * 100
    trans = {f"{a}_{b}": transitions(res.segs[a], res.segs[b], res.pix_ha)
             for a, b in [*zip(res.years, res.years[1:]), (y0, y1)]}
    info = pd.DataFrame(METRIC_INFO, index=["description", "unit"]).T.rename_axis("metric")
    params = pd.Series({**res.seg_params, "pixel_height_m": res.py, "pixel_width_m": res.px},
                       name="value").rename_axis("parameter")

    csv = {
        "landscape_metrics.csv": lambda p: res.metrics.to_csv(p),
        "fragmentation_area_ha.csv": lambda p: res.composition.to_csv(p),
        "fragmentation_share_pct.csv": lambda p: comp_pct.to_csv(p),
        "patches.csv": lambda p: res.patches.to_csv(p, index=False),
    }
    sheets = {
        "landscape_metrics": res.metrics, "metric_definitions": info,
        "class_area_ha": res.composition, "class_share_pct": comp_pct,
        **{f"transition_{k}": t for k, t in trans.items()},
        "patch_size_summary": res.patches.groupby("year")["area"].describe(),
        "parameters": params,
    }
    with tqdm(total=len(csv) + len(sheets), desc="Tables", unit="table") as bar:
        for name, write in csv.items():
            write(d / name)
            bar.update()
        with pd.ExcelWriter(d / "mangrove_fragmentation.xlsx") as xl:
            for name, df in sheets.items():
                df.to_excel(xl, sheet_name=name)
                bar.update()
    return d


def export_interactive(res, out_dir=OUT_DIR, only=None):
    """Write the interactive HTML files (all, or just the names in `only`); returns their paths."""
    d = Path(out_dir) / "interactive"
    d.mkdir(parents=True, exist_ok=True)
    y0, y1 = res.years[0], res.years[-1]
    html = {
        "fragmentation_map": lambda p: p.write_text(web_map(res), encoding="utf-8"),
        f"sankey_{y0}_{y1}": lambda p: sankey(res.segs, [y0, y1], res.pix_ha).write_html(p),
        "sankey_all_years": lambda p: sankey(res.segs, res.years, res.pix_ha).write_html(p),
    }
    if only is not None:
        html = {k: html[k] for k in only}
    for name, write in tqdm(html.items(), desc="Interactive HTML", unit="file"):
        write(d / f"{name}.html")
    return [d / f"{n}.html" for n in html]


def export_all(res, out_dir=OUT_DIR, figures=True):
    if figures:
        export_figures(res, out_dir)
    export_rasters(res, out_dir)
    export_tables(res, out_dir)
    export_interactive(res, out_dir)
    return Path(out_dir)


# ---------------------------------------------------------------- self-check

def _selfcheck():
    m = np.zeros((200, 200), bool)
    m[20:180, 20:180] = True     # big block -> large core + edge
    m[98:102, 98:102] = False    # 1.4 ha hole inside -> perforated ring
    m[5:8, 190:193] = True       # tiny isolated blob -> patch
    s = segment(m, 30.0, 30.0)
    assert s[0, 0] == 0, "non-mangrove"
    assert s[6, 191] == 1, "patch"
    assert s[21, 100] == 2, "edge"
    assert s[99, 97] == 3, "perforated"
    assert s[60, 60] == 6, "large core"
    assert _aggregation_index(np.ones((10, 10), bool)) == 100
    print("self-check OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _selfcheck()
    else:
        r = analyze()
        print(r.metrics.round(3).T)
        print("written to", export_all(r))
