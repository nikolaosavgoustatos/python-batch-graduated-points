import arcpy
import math
import traceback

import numpy as np

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
LAYER_FIELDS = {
    "As": "As mg/kg",
    "Ba": "Ba mg/kg",
    "Ca": "Ca mg/kg",
    "Cr": "Cr mg/kg",
    "Cu": "Cu mg/kg",
    "Fe": "Fe mg/kg",
    "Mn": "Mn mg/kg",
    "Ni": "Ni mg/kg",
    "Pb": "Pb mg/kg",
    "Rb": "Rb mg/kg",
    "Sr": "Sr mg/kg",
    "Ti": "Ti mg/kg",
    "V": "V mg/kg",
    "Zn": "Zn mg/kg",
}

PERCENTILES = [5, 25, 50, 75, 90, 95]
NUM_CLASSES = 7
MIN_SIZE = 4.0
MAX_SIZE = 18.0
SYMBOL_SIZES = [
    MIN_SIZE + (MAX_SIZE - MIN_SIZE) * i / (NUM_CLASSES - 1)
    for i in range(NUM_CLASSES)
]

# Biggest symbol on lowest concentration; smallest on highest.
REVERSE_SIZE_ORDER = True

DEFAULT_GALLERY_SYMBOL = "Circle 1"


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
    return [round_half_up(b) for b in breaks]


def _size_order(num_classes=NUM_CLASSES):
    order = list(range(num_classes))
    if REVERSE_SIZE_ORDER:
        order.reverse()
    return order


# ---------------------------------------------------------------------------
# Percentile breaks from sample points
# ---------------------------------------------------------------------------
def get_percentile_breaks_from_layer(layer, field, pct_list):
    """Build 8 break points (7 classes) from the layer's source features."""
    fc = layer.dataSource if layer.dataSource else layer.name
    vals = []
    with arcpy.da.SearchCursor(fc, [field]) as cursor:
        for row in cursor:
            if row[0] is not None:
                vals.append(row[0])
    if not vals:
        raise ValueError(f"No valid values found for field '{field}' in {fc}.")

    arr = np.array(vals, dtype=float)
    breaks = [float(np.min(arr))]
    for p in pct_list:
        breaks.append(float(np.percentile(arr, p)))
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


def _commit(sym, layer):
    layer.symbology = sym
    return layer.symbology


def _cim_break_count(layer):
    for version in ("V3", "V2"):
        try:
            renderer = layer.getDefinition(version).renderer
            if hasattr(renderer, "breaks"):
                return len(renderer.breaks)
        except Exception:
            continue
    return 0


def _set_marker_properties(symbol_ref, size):
    """Adjust marker size, color, and outline in-place on an existing CIM symbol reference."""
    if symbol_ref is None or getattr(symbol_ref, "symbol", None) is None:
        return
    point_symbol = symbol_ref.symbol
    if not hasattr(point_symbol, "symbolLayers"):
        return
    for symbol_layer in point_symbol.symbolLayers:
        layer_type = type(symbol_layer).__name__
        
        # 1. Update the overall size
        if layer_type in (
            "CIMVectorMarker",
            "CIMCharacterMarker",
            "CIMPictureMarker",
            "CIMShapeMarker",
        ) and hasattr(symbol_layer, "size"):
            symbol_layer.size = float(size)
            
        # 2. Update the fill color, outline color, and outline width for Circle 1 (Vector Marker)
        if layer_type == "CIMVectorMarker" and hasattr(symbol_layer, "markerGraphics"):
            for graphic in getattr(symbol_layer, "markerGraphics", []):
                g_sym = getattr(graphic, "symbol", None)
                if g_sym and hasattr(g_sym, "symbolLayers"):
                    for inner_layer in g_sym.symbolLayers:
                        inner_type = type(inner_layer).__name__
                        if inner_type == "CIMSolidFill" and hasattr(inner_layer, "color"):
                            # Fuchsia Fill
                            inner_layer.color.values = [255, 0, 255, 100]
                        elif inner_type == "CIMSolidStroke":
                            # Black Outline
                            if hasattr(inner_layer, "color"):
                                inner_layer.color.values = [0, 0, 0, 100]
                            # Outline Width
                            if hasattr(inner_layer, "width"):
                                inner_layer.width = 0.7


def _create_graduated_breaks(layer, field, num_classes):
    """Create GraduatedSymbolsRenderer and commit so class breaks exist."""
    sym = layer.symbology
    sym.updateRenderer("GraduatedSymbolsRenderer")
    sym.renderer.classificationField = field
    sym.renderer.normalizationType = " "
    sym.renderer.breakCount = num_classes
    sym.renderer.classificationMethod = "EqualInterval"
    sym = _commit(sym, layer)

    if sym.renderer.type != "GraduatedSymbolsRenderer":
        raise RuntimeError(
            f"Layer '{layer.name}' could not be switched to GraduatedSymbolsRenderer."
        )

    class_breaks = sym.renderer.classBreaks
    if len(class_breaks) != num_classes:
        sym.renderer.breakCount = num_classes
        sym = _commit(sym, layer)
        class_breaks = sym.renderer.classBreaks

    if len(class_breaks) != num_classes:
        raise RuntimeError(
            f"Expected {num_classes} class breaks, got {len(class_breaks)}."
        )
    return sym, class_breaks


def _apply_gallery_circle_to_breaks(class_breaks, num_classes):
    """Apply gallery Circle 1 to each class break via arcpy.mp (drawable symbols)."""
    sizes = _size_order(num_classes)
    for i, class_break in enumerate(class_breaks):
        class_break.symbol.applySymbolFromGallery(DEFAULT_GALLERY_SYMBOL)
        class_break.symbol.size = SYMBOL_SIZES[sizes[i]]


def _apply_manual_breaks_cim(layer, field, layer_name, rounded_breaks, labels, num_classes):
    """
    Set manual percentile breaks in-place on the existing CIM renderer.
    Does NOT replace symbols or rebuild the renderer (avoids blank template /
    black dots / lost class breaks).
    """
    sizes = _size_order(num_classes)
    last_exc = None

    for version in ("V3", "V2"):
        try:
            cim_layer = layer.getDefinition(version)
            renderer = cim_layer.renderer
            if type(renderer).__name__ != "CIMClassBreaksRenderer":
                raise RuntimeError(
                    f"Expected CIMClassBreaksRenderer, got {type(renderer).__name__}."
                )
            if len(renderer.breaks) != num_classes:
                raise RuntimeError(
                    f"CIM has {len(renderer.breaks)} breaks, expected {num_classes}."
                )

            renderer.classBreakType = "GraduatedSymbol"
            renderer.classificationMethod = "Manual"
            renderer.field = field
            renderer.fields = [field]
            
            # --- FIX: Set the heading to match the layer name instead of the raw field name ---
            renderer.heading = layer_name 
            
            renderer.minimumBreak = float(rounded_breaks[0])
            renderer.showInAscendingOrder = False

            for i in range(num_classes):
                class_break = renderer.breaks[i]
                class_break.upperBound = float(rounded_breaks[i + 1])
                class_break.label = labels[i]
                _set_marker_properties(class_break.symbol, SYMBOL_SIZES[sizes[i]])

            if renderer.breaks:
                renderer.defaultSymbol = renderer.breaks[0].symbol

            cim_layer.expanded = False
            layer.setDefinition(cim_layer)
            return
        except Exception as exc:
            last_exc = exc
            continue

    raise RuntimeError(f"Could not apply manual CIM breaks: {last_exc}")


# ---------------------------------------------------------------------------
# Symbology application
# ---------------------------------------------------------------------------
def apply_graduated_symbols(layer, field, layer_name, breaks, labels, num_classes=NUM_CLASSES):
    """
    Hybrid workflow:
      1. arcpy.mp  — create renderer + gallery Circle 1 on each break (symbols)
      2. CIM in-place — manual break values, labels, legend order, sizes & properties
    """
    rounded_breaks = build_rounded_breaks(breaks)

    sym, class_breaks = _create_graduated_breaks(layer, field, num_classes)
    _apply_gallery_circle_to_breaks(class_breaks, num_classes)
    _commit(sym, layer)

    _apply_manual_breaks_cim(layer, field, layer_name, rounded_breaks, labels, num_classes)

    if _cim_break_count(layer) != num_classes:
        raise RuntimeError(
            f"CIM verification failed: expected {num_classes} breaks, "
            f"got {_cim_break_count(layer)}."
        )

    return rounded_breaks, labels


def apply_symbology_for_field(active_map, layer_name, field, breaks, labels):
    layer = ensure_layer_on_map(active_map, layer_name)
    last_exc = None
    for attempt in (1, 2):
        try:
            apply_graduated_symbols(layer, field, layer_name, breaks, labels)
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

    failed_fields = []
    print("=== Applying Graduated Symbols (ArcGIS Circle 1, 7 classes, Manual) ===")
    print(f"    Symbols: {DEFAULT_GALLERY_SYMBOL} via ClassBreak.symbol")
    print(f"    Properties: Fuchsia fill, Black outline, 0.7 pt width")
    print(f"    Breaks:  manual via CIM in-place edit")
    print(f"    Symbol sizes: {SYMBOL_SIZES}")
    print(f"    REVERSE_SIZE_ORDER = {REVERSE_SIZE_ORDER}")

    for field, layer_name in LAYER_FIELDS.items():
        try:
            layer = ensure_layer_on_map(active_map, layer_name)
        except RuntimeError as exc:
            print(f"  {field:4s}: FATAL - {exc}")
            failed_fields.append(field)
            continue

        try:
            breaks = get_percentile_breaks_from_layer(layer, field, PERCENTILES)
            labels = build_class_labels(breaks)
            layer, ok = apply_symbology_for_field(
                active_map, layer_name, field, breaks, labels
            )
            status = "OK" if ok else "FAILED"
            print(f"  {field:4s}: {status}   breaks = {build_rounded_breaks(breaks)}")
            if not ok:
                failed_fields.append(field)
        except Exception as exc:
            print(f"  {field:4s}: ERROR - {exc}")
            print(traceback.format_exc())
            failed_fields.append(field)

    try:
        arcpy.RefreshTOC()
        arcpy.RefreshActiveView()
    except Exception:
        pass

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
