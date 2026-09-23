# Input data (not included)

The map files are shared separately, not with the code.

Put them here, in a folder named `mangrove_1990-2024`:

```
data/
└── mangrove_1990-2024/
    ├── classification_1990_Class5.tif
    ├── classification_1995_Class5.tif
    └── ...
```

To use a different folder name, change `DATA_DIR` in the first code cell of the notebook, e.g. `DATA_DIR = Path("data/my_maps")`.

Each map must be a GeoTIFF (`.tif`), one file per year, with the year in the file name. Pixel value **1** is mangrove and **0** is not mangrove. All years must cover the same area on the same pixel grid.
