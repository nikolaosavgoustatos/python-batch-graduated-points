# ArcGIS Pro Graduated Symbols Automator (CIM & arcpy.mp)

This repository contains a Python script for ArcGIS Pro that automates the application of highly customized Graduated Symbols symbology to multiple point feature layers. 

By leveraging a hybrid approach using `arcpy.mp` and the Cartographic Information Model (CIM), this script bypasses standard UI limitations to programmatically define precise class breaks, reverse sizing logic, and deep symbol property formatting without breaking the layer renderer.

## Features

* **Automated Percentile Classification:** Calculates 7 manual class breaks based on exact sample percentiles (Min, 5th, 25th, 50th, 75th, 90th, 95th, Max) directly from the feature class data.
* **Custom Sizing & Reversed Ordering:** Scales point symbols linearly from **4 pt to 18 pt**. It implements a reversed size order logic (largest symbols represent the lowest concentrations) and forces the legend to display in descending order.
* **Deep CIM Symbol Customization:** Modifies the default "Circle 1" gallery symbol in-place to apply:
  * **Fill Color:** Fuchsia 
  * **Outline Color:** Black 
  * **Outline Width:** 0.7 pt
* **Smart Legend Formatting:** 
  * Applies standard half-up rounding (always showing exactly 1 decimal place).
  * Generates clean, contiguous `(x, y]` range labels (e.g., `5.1 - 10.5`).
  * Replaces the default raw field name heading with the formatted Layer Name (e.g., replacing "As" with "As mg/kg").

## Prerequisites

* **Environment:** ArcGIS Pro 2.x or 3.x (uses Python 3).
* **Project State:** The script must be run within an open ArcGIS Pro project (`"CURRENT"`).
* **Map State:** An active map must be open, and the point layers you intend to symbolize must already be added to the Contents pane.

## Usage

1. Open your ArcGIS Pro project.
2. Ensure the target point feature layers are present in your active map.
3. Open the **Python Window** or an **ArcGIS Notebook** inside ArcGIS Pro.
4. Copy and paste the script, then execute it. 
5. The map and Table of Contents (TOC) will automatically refresh to display the newly symbolized layers.

## Configuration

You can easily adapt this script for your own datasets by modifying the variables at the top of the script:

### 1. Layer and Field Mapping
Update the `LAYER_FIELDS` dictionary to match your specific map layers and their corresponding fields.

```python
LAYER_FIELDS = {
    # "Raw Field Name": "Layer Name in Contents Pane"
    "As": "As mg/kg",
    "Ba": "Ba mg/kg",
    # Add your own mappings here...
}

```

### 2. Sizing and Classes

Adjust the minimum size, maximum size, and the number of classes if you need different visual scaling:

```python
PERCENTILES = [5, 25, 50, 75, 90, 95] # Define your percentile breaks here
NUM_CLASSES = 7
MIN_SIZE = 4.0
MAX_SIZE = 18.0
REVERSE_SIZE_ORDER = True # Set to False for standard (low=small, high=large) sizing

```

## Technical Notes

Applying manual breaks to a Graduated Symbols renderer via `arcpy` can sometimes result in blank template symbols or lost class breaks. This script solves that by using a two-step hybrid workflow:

1. **`arcpy.mp`:** Generates the baseline Graduated Symbols renderer, applies Equal Interval (to initialize the breaks), and binds the baseline gallery shape ("Circle 1").
2. **CIM (`getDefinition`)**: Re-enters the layer's definition to safely overwrite the classification method to "Manual", inject exact percentile break thresholds, apply custom string labels, fix the legend heading, and drill down into the `symbolLayers` array to alter vector stroke/fill colors.
