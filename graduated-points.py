"""
Graduated Symbols symbology for point features.

For each element field in IN_POINTS:
  - Graduated Symbols (point layer)
  - Fuchsia color ramp (7 stops: very light pink -> deep magenta)
  - Manual interval, 7 classes
  - Break VALUES: min -> 5th -> 25th -> 50th -> 75th -> 90th -> 95th -> max
  - Rounding: half-up, 1 decimal (same logic as IDW code)
  - Labels: contiguous (x, y] ranges, 1 decimal place.
  - Legend: descending order (highest concentrations on top).

Run inside ArcGIS Pro (CURRENT project must be open).

FIX vs previous version:
  The old code relied on arcpy.mp's "set classificationMethod=EqualInterval,
  breakCount=7, then switch to ManualInterval" trick to get Pro to
  auto-generate 7 CIMClassBreak objects. That trick is unreliable when run
  headlessly (no Contents-pane redraw) -- classBreaks kept coming back
  length 0 for every field. This version never depends on arcpy.mp to
  generate breaks: it builds the CIMClassBreaksRenderer and every
  CIMClassBreak object directly via the CIM API, so there's nothing for
  Pro to "auto-generate" and nothing to race against.
"""

import arcpy
import copy
import math
import traceback

import numpy as np

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
IN_POINTS = "As mg/kg"
Z_FIELDS = [
    "As", "Ba", "Ca", "Cr", "Cu", "Fe", "Mn", "Ni",
    "Pb", "Rb", "Sr", "Ti", "V", "Zn",
]

PERCENTILES = [5, 25, 50, 75, 90, 95]
NUM_CLASSES = 7

# Symbol sizes (pt) — smallest class -> largest class
SYMBOL_SIZES = [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0]

# Fuchsia ramp: 7 stops from very light pink -> deep magenta
FUCHSIA_RGB = [
    (255, 230, 240),   # 1: very light pink
    (255, 200, 220),   # 2: light pink
    (255, 150, 200),   # 3: pink
    (255, 100, 180),   # 4: bright pink
    (255,  50, 160),   # 5: fuchsia
    (220,   0, 130),   # 6: deep fuchsia
    (180,   0, 110),   # 7: dark magenta
]

OUTLINE_RGB = (60, 0, 40)
OUTLINE_WIDTH = 0.5


# ---------------------------------------------------------------------------
# Rounding / formatting helpers
# ---------------------------------------------------------------------------
def round_half_up(value, decimals=1):
    """Standard half-up rounding (e.g. 5.05 -> 5.1)."""
    multiplier = 10 ** decimals
    return math.floor(float(value) * multiplier + 0.5) / multiplier


def format_decimal(value):
    """Always display exactly one decimal place."""
    return f"{value:.1f}"


def build_class_labels(breaks):
    """Build legend labels from percentile values using half-up rounding."""
    labels = []
    for i in range(len(breaks) - 1):
        if i == 0:
            lower = round_half_up(breaks[0])
        else:
            previous_upper = round_half_up(breaks[i])
            lower = previous_upper + 0.1
        upper = round_half_up(breaks[i + 1])
        labels.append(f"{format_decimal(lower)} - {format_decimal(upper)}")
    return labels


def build_rounded_breaks(breaks):
    """Round all break values with half-up rounding (1 decimal)."""
    rounded = [round_half_up(breaks[0])]
    for i in range(1, len(breaks)):
        rounded.append(round_half_up(breaks[i]))
    return rounded


# ---------------------------------------------------------------------------
# Percentile breaks from sample points
# ---------------------------------------------------------------------------
def get_percentile_breaks_from_points(points_fc, field, pct_list):
    """Build 8 break points (7 classes) from sample points."""
    vals = []
    with arcpy.da.SearchCursor(points_fc, [field]) as cursor:
        for row in cursor:
            if row[0] is not None:
                vals.append(row[0])

    if not vals:
        raise ValueError(f"No valid values found for field '{field}' in {points_fc}.")

    arr = np.array(vals, dtype=float)
    breaks = [float(np.min(arr))]
    for p in pct_list:
        v = float(np.percentile(arr, p))
        breaks.append(v)
    breaks.append(float(np.max(arr)))

    for i in range(1, len(breaks)):
        if breaks[i] <= breaks[i - 1]:
            breaks[i] = breaks[i - 1] + 1e-6

    return breaks


# ---------------------------------------------------------------------------
# Layer helpers
# ---------------------------------------------------------------------------
def find_feature_layer(active_map, layer_name):
    for layer in active_map.listLayers():
        if not layer.isRasterLayer and layer.name == layer_name:
            return layer
    return None


def ensure_layer_on_map(active_map, layer_name):
    layer = find_feature_layer(active_map, layer_name)
    if layer is None:
        raise RuntimeError(
            f"Layer '{layer_name}' not found on the active map. "
            "Add the point feature class to the map first."
        )
    return layer


# ---------------------------------------------------------------------------
# CIM color / symbol helpers
# ---------------------------------------------------------------------------
def make_cim_color(r, g, b, alpha=100):
    color = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V2")
    color.r = r
    color.g = g
    color.b = b
    color.alpha = alpha
    color.useGamma = False
    return color


def update_symbol_color(sym, r, g, b, alpha=100):
    """Recursively update the color of a CIM symbol and its nested layers."""
    if sym is None:
        return

    cim_color = make_cim_color(r, g, b, alpha)
    stroke_color = make_cim_color(*OUTLINE_RGB, alpha=100)

    if hasattr(sym, 'symbolLayers') and sym.symbolLayers:
        for layer in sym.symbolLayers:
            layer_type = type(layer).__name__
            if layer_type == "CIMSolidFill":
                layer.color = cim_color
            elif layer_type == "CIMSolidStroke":
                layer.color = stroke_color
                layer.width = OUTLINE_WIDTH

            if hasattr(layer, 'symbol') and layer.symbol is not None:
                update_symbol_color(layer.symbol, r, g, b, alpha)
            if hasattr(layer, 'graphics') and layer.graphics:
                for g_obj in layer.graphics:
                    if hasattr(g_obj, 'symbol') and g_obj.symbol is not None:
                        update_symbol_color(g_obj.symbol, r, g, b, alpha)


def set_symbol_size(sym, size):
    """Set the size on a CIM point symbol (top-level marker size)."""
    try:
        sym.symbolLayers[0].size = size
    except Exception:
        pass
    # some marker layers also carry size on the outer CIMPointSymbol
    if hasattr(sym, 'symbolLayers') and sym.symbolLayers:
        for layer in sym.symbolLayers:
            if hasattr(layer, 'size'):
                try:
                    layer.size = size
                except Exception:
                    pass


def get_template_point_symbol(layer):
    """
    Grab a deep copy of the layer's current point symbol to use as a
    template for every class break. Works whether the layer currently has
    a SimpleRenderer or an already-applied ClassBreaksRenderer from a
    previous run.
    """
    cim_layer = layer.getDefinition("V2")
    renderer = cim_layer.renderer

    template = None
    renderer_type = type(renderer).__name__

    if renderer_type == "CIMSimpleRenderer" and renderer.symbol is not None:
        template = renderer.symbol.symbol
    elif renderer_type == "CIMClassBreaksRenderer" and renderer.breaks:
        first_break = renderer.breaks[0]
        if first_break.symbol is not None:
            template = first_break.symbol.symbol

    if template is None:
        raise RuntimeError(
            f"Could not find an existing point symbol on layer "
            f"'{layer.name}' to use as a template. Apply a simple point "
            f"symbol to the layer first."
        )

    return copy.deepcopy(template)


# ---------------------------------------------------------------------------
# Symbology Application (pure CIM — no arcpy.mp auto-classification)
# ---------------------------------------------------------------------------
def apply_graduated_symbols(layer, field, breaks, labels, template_symbol,
                             num_classes=NUM_CLASSES):
    """Apply Graduated Symbols entirely through the CIM API."""
    rounded_breaks = build_rounded_breaks(breaks)

    cim_layer = layer.getDefinition("V2")

    renderer = arcpy.cim.CreateCIMObjectFromClassName("CIMClassBreaksRenderer", "V2")
    renderer.classBreakType = "GraduatedSymbol"
    renderer.classificationMethod = "Manual"
    renderer.field = field
    renderer.minimumBreak = float(rounded_breaks[0])
    renderer.showInAscendingOrder = False

    cim_breaks = []
    for i in range(num_classes):
        cb = arcpy.cim.CreateCIMObjectFromClassName("CIMClassBreak", "V2")
        cb.upperBound = float(rounded_breaks[i + 1])
        cb.label = labels[i]

        sym = copy.deepcopy(template_symbol)
        r, g, b = FUCHSIA_RGB[i]
        update_symbol_color(sym, r, g, b, alpha=100)
        set_symbol_size(sym, SYMBOL_SIZES[i])

        sym_ref = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V2")
        sym_ref.symbol = sym
        cb.symbol = sym_ref

        cim_breaks.append(cb)

    renderer.breaks = cim_breaks

    cim_layer.renderer = renderer
    cim_layer.expanded = False
    layer.setDefinition(cim_layer)

    # Sanity check — confirm it actually took
    check = layer.getDefinition("V2").renderer
    if type(check).__name__ != "CIMClassBreaksRenderer" or len(check.breaks) != num_classes:
        raise RuntimeError(
            f"Renderer did not apply correctly. Got "
            f"{len(getattr(check, 'breaks', []))} breaks."
        )

    return rounded_breaks, labels


def apply_symbology_for_field(active_map, field, breaks, labels, template_symbol):
    layer_name = IN_POINTS
    layer = ensure_layer_on_map(active_map, layer_name)

    last_exc = None
    for attempt in (1, 2):
        try:
            apply_graduated_symbols(layer, field, breaks, labels, template_symbol)
        except Exception as exc:
            last_exc = exc
            print(f"    {layer_name} / {field}: attempt {attempt} raised: {exc}")
            print(traceback.format_exc())
            continue
        return layer, True

    if last_exc is not None:
        print(f"    {layer_name} / {field}: last error was: {last_exc}")
    return layer, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    active_map = aprx.activeMap
    if not active_map:
        raise RuntimeError("No active map found in the CURRENT project.")

    try:
        layer = ensure_layer_on_map(active_map, IN_POINTS)
    except RuntimeError as exc:
        print(f"FATAL: {exc}")
        return

    try:
        template_symbol = get_template_point_symbol(layer)
    except RuntimeError as exc:
        print(f"FATAL: {exc}")
        return

    failed_fields = []

    print(f"=== Applying Graduated Symbols (fuchsia, 7 classes, manual) to '{IN_POINTS}' ===")
    for field in Z_FIELDS:
        try:
            breaks = get_percentile_breaks_from_points(IN_POINTS, field, PERCENTILES)
            labels = build_class_labels(breaks)
            layer, ok = apply_symbology_for_field(active_map, field, breaks, labels, template_symbol)
            status = "OK" if ok else "FAILED"
            print(f"  {field:4s}: {status}   breaks = {build_rounded_breaks(breaks)}")
            if not ok:
                failed_fields.append(field)
        except Exception as exc:
            print(f"  {field}: ERROR - {exc}")
            print(traceback.format_exc())
            failed_fields.append(field)

    try:
        if aprx.activeView:
            aprx.activeView.refresh()
    except Exception:
        pass

    try:
        aprx.save()
    except Exception:
        pass

    failed_fields = sorted(set(failed_fields))
    if failed_fields:
        print(f"\nFields needing attention: {failed_fields}")
    else:
        print("\nAll fields processed successfully.")
    print("Done.")


if __name__ == "__main__":
    main()
