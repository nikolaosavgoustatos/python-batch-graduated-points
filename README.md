# ArcGIS Pro Geochemical Graduated Symbols

A Python automation script for ArcGIS Pro that applies precise **Graduated Symbols** symbology to multiple geochemical point layers. It calculates statistical percentile breaks, applies custom scaling, and enforces specific aesthetic styles (Fuchsia fill, Black outline) using a robust hybrid `arcpy.mp` and Cartographic Information Model (CIM) approach.

## Features

- **Batch Processing:** Iterates through a predefined list of elements (As, Ba, Cu, Zn, etc.) and their corresponding map layers.
- **Statistical Breaks:** Automatically calculates 7 class breaks based on specific percentiles (Min, 5th, 25th, 50th, 75th, 90th, 95th, Max) directly from the layer's attribute table.
- **Custom Styling:** Applies the ArcGIS Pro default "Circle 1" template but overrides the colors to use a **Fuchsia fill** and **Black outline (0.7 pt width)**.
- **Linear Scaling:** Scales symbol sizes linearly from 4 pt (minimum value) to 18 pt (maximum value).
- **Reverse Size Option:** Configurable to display the largest symbols on the lowest concentrations and smallest symbols on the highest (useful for specific geochemical visualization standards).
- **Smart Labeling:** Generates contiguous legend labels (e.g., `1.0 - 5.5`) using standard half-up rounding to 1 decimal place.
- **CIM Integration:** Uses ArcGIS Pro's CIM API in-place to set manual breaks, descending legend order, and exact symbol sizes without destroying the applied gallery symbols.

## Prerequisites

- **ArcGIS Pro** (Version 2.9 or newer recommended for full CIM V3 support, though V2 fallback is included).
- **Python 3.x** (installed automatically with ArcGIS Pro).
- **NumPy** (included in the standard ArcGIS Pro Python environment).

## Setup and Configuration

Before running the script, ensure your ArcGIS Pro project is set up correctly:

1. **Add Layers:** Add all target point feature layers to your active map.
2. **Name Layers:** Ensure the layer names in the map exactly match the values in the `LAYER_FIELDS` dictionary (e.g., `"As mg/kg"`, `"Cu mg/kg"`).
3. **Fields:** Ensure the layers contain the corresponding attribute fields (e.g., `"As"`, `"Cu"`).

You can easily modify the configuration block at the top of the script to suit your data:

```python
LAYER_FIELDS = {
    "As": "As mg/kg",
    "Ba": "Ba mg/kg",
    # Add or remove elements here
}

PERCENTILES = [5, 25, 50, 75, 90, 95]
NUM_CLASSES = 7
MIN_SIZE = 4.0
MAX_SIZE = 18.0
REVERSE_SIZE_ORDER = True  # Set to False for normal scaling (small to large)

# Colors [R, G, B, Alpha]
FILL_COLOR = {'RGB': [255, 0, 255, 100]}    # Fuchsia
OUTLINE_COLOR = {'RGB': [0, 0, 0, 100]}     # Black
OUTLINE_WIDTH = 0.7
```

## Usage

Because this script relies on the `"CURRENT"` project context, it must be run from inside an open ArcGIS Pro session.

### Option 1: ArcGIS Pro Python Pane
1. Open your ArcGIS Project.
2. Go to the **Analysis** tab -> **Python**.
3. Paste the entire script into the Python console and press `Enter`.

### Option 2: ArcGIS Pro Python Environment (External IDE)
1. Open your ArcGIS Project.
2. Open your preferred IDE (PyCharm, VS Code, Jupyter) using the ArcGIS Pro Python environment (`arcgispro-py3`).
3. Run the script. 

*Note: The script will refresh the Table of Contents (TOC), active view, and attempt to save the project upon completion.*

## How It Works

Directly manipulating Graduated Symbols via the standard `arcpy.mp` API often results in lost symbols or reverted colors when applying manual breaks. To prevent this, the script uses a hybrid workflow:

1. **`arcpy.mp` Application:** Creates the `GraduatedSymbolsRenderer`, applies the "Circle 1" gallery symbol, and sets the Fuchsia fill and sizes.
2. **CIM In-Place Edit:** Fetches the layer's definition (`getDefinition`), directly modifies the renderer's `upperBound` and `label` arrays, digs into the `CIMVectorMarker` graphics to force the outline color to Black and width to `0.7`, and sets `showInAscendingOrder = False` for descending legend order.
3. **Verification:** Confirms the CIM breaks match the expected class count before committing.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (or just use it freely for your geochemical mapping needs!).
