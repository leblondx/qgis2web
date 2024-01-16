import os
import math
import json

_warnings = []

def convert(geostyler):
    global _warnings
    _warnings = []
    if not isinstance(geostyler, list):
        geostyler = [geostyler]
    name = geostyler[0]["name"] if len(geostyler) == 1 else "Style"

    layers = []
    for g in geostyler:
        layers.extend(processLayer(g))
    obj = {
        "version": 8,
        "name": name,
        "glyphs": "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",
        "sources": {g["name"]: "TODO:Configure this!!!" for g in geostyler},
        "layers":  layers,
        "sprite": "spriteSheet"
    }

    return json.dumps(obj, indent=4), _warnings


def _toZoomLevel(scale):
    return 30 if scale < 1 else int(math.log(1000000000 / scale, 2))


def processLayer(layer):
    allLayers = []

    for rule in layer.get("rules", []):
        layers = processRule(rule, layer["name"])
        allLayers += layers

    return allLayers


def processRule(rule, source):
    filt = convertExpression(rule.get("filter", None))
    minzoom = None
    maxzoom = None
    if "scaleDenominator" in rule:
        scale = rule["scaleDenominator"]
        if "max" in scale:
            maxzoom = _toZoomLevel(scale["max"])
        if "min" in scale:
            minzoom = _toZoomLevel(scale["min"])
    name = rule.get("name", "rule")
    layers = [processSymbolizer(s) for s in rule["symbolizers"]]
    for i, lay in enumerate(layers):
        try:
            if filt is not None:
                lay["filter"] = filt
            lay["source"] = source
            lay["id"] = f"{name}:{str(i)}"
            if minzoom is not None:
                lay["minzoom"] = minzoom
            if maxzoom is not None:
                lay["maxzoom"] = maxzoom
        except Exception as e:
            _warnings.append(f"Empty style rule: '{name}:{str(i)}'")
    return layers


func = {
    "PropertyName": "get",
    "Or": "any",
    "And": "all",
    "PropertyIsEqualTo": "==",
    "PropertyIsNotEqualTo": "!=",
    "PropertyIsLessThanOrEqualTo": "<=",
    "PropertyIsGreaterThanOrEqualTo": ">=",
    "PropertyIsLessThan": "<",
    "PropertyIsGreaterThan": ">",
    "Add": "+",
    "Sub": "-",
    "Mul": "*",
    "Div": "/",
    "Not": "!",
    "toRadians": None,
    "toDegrees": None,
    "floor": "floor",
    "ceil": "ceil",
    "if_then_else": "case",
    "Concatenate": "concat",
    "strSubstr": None,
    "strToLower": "downcase",
    "strToUpper": "upcase",
    "strReplace": None,
    "acos": "acos",
    "asin": "asin",
    "atan": "atan",
    "atan2": "atan2",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "log": "ln",
    "strCapitalize": None,
    "min": "min",
    "max": "max",
}  # TODO


def convertExpression(exp):
    if exp is None:
        return None
    if not isinstance(exp, list):
        return exp
    funcName = func.get(exp[0], None)
    if funcName is None:
        _warnings.append(
            f"Unsupported expression function for mapbox conversion: '{exp[0]}'"
        )
        return None
    else:
        convertedExp = [funcName]
        convertedExp.extend(convertExpression(arg) for arg in exp[1:])
        return convertedExp


def processSymbolizer(sl):
    symbolizerType = sl["kind"]
    if symbolizerType == "Fill":
        symbolizer = _fillSymbolizer(sl)
    elif symbolizerType == "Icon":
        symbolizer = _iconSymbolizer(sl)
    elif symbolizerType == "Line":
        symbolizer = _lineSymbolizer(sl)
    elif symbolizerType == "Mark":
        symbolizer = _markSymbolizer(sl)
    elif symbolizerType == "Raster":
        symbolizer = _rasterSymbolizer(sl)

    elif symbolizerType == "Text":
        symbolizer = _textSymbolizer(sl)
    geom = _geometryFromSymbolizer(sl)
    if geom is not None:
        _warnings.append("Derived geometries are not supported in mapbox gl")

    return symbolizer


def _symbolProperty(sl, name):
    return convertExpression(sl[name]) if name in sl else None


def _textSymbolizer(sl):
    layout = {}
    paint = {}
    color = _symbolProperty(sl, "color")
    fontFamily = _symbolProperty(sl, "font")
    label = _symbolProperty(sl, "label")
    size = _symbolProperty(sl, "size")
    if "offset" in sl:
        offset = sl["offset"]
        offsetx = convertExpression(offset[0])
        offsety = convertExpression(offset[1])
        layout["text-offset"] = [offsetx, offsety]
    elif "perpendicularOffset" in sl:
        offset = sl["perpendicularOffset"]
        layout["text-offset"] = offset

    if "haloColor" in sl and "haloSize" in sl:
        paint["text-halo-width"] = _symbolProperty(sl, "haloSize")
        paint["text-halo-color"] = _symbolProperty(sl, "haloColor")

    layout["text-field"] = label
    layout["text-size"] = size
    layout["text-font"] = [fontFamily]

    paint["text-color"] = color

    """
    rotation = -1 * float(qgisLayer.customProperty("labeling/angleOffset"))
    layout["text-rotate"] = rotation

    ["text-opacity"] = (255 - int(qgisLayer.layerTransparency())) / 255.0

    if str(qgisLayer.customProperty("labeling/scaleVisibility")).lower() == "true":
        layer["minzoom"]  = _toZoomLevel(float(qgisLayer.customProperty("labeling/scaleMin")))
        layer["maxzoom"]  = _toZoomLevel(float(qgisLayer.customProperty("labeling/scaleMax")))
    """

    return {"type": "symbol", "paint": paint, "layout": layout}


def _lineSymbolizer(sl, graphicStrokeLayer=0):
    opacity = _symbolProperty(sl, "opacity")
    color = sl.get("color", None)
    graphicStroke = sl.get("graphicStroke", None)
    width = _symbolProperty(sl, "width")
    dasharray = _symbolProperty(sl, "dasharray")
    cap = _symbolProperty(sl, "cap")
    join = _symbolProperty(sl, "join")
    offset = _symbolProperty(sl, "offset")

    paint = {}
    if graphicStroke is not None:
        _warnings.append("Marker lines not supported for Mapbox GL conversion")
        # TODO

    if color is None:
        paint["visibility"] = "none"
    else:
        paint["line-width"] = width
        paint["line-opacity"] = opacity
        paint["line-color"] = color
    if dasharray is not None:
        paint["line-dasharray"] = dasharray
    if offset is not None:
        paint["line-offset"] = offset

    return {"type": "line", "paint": paint}


def _geometryFromSymbolizer(sl):
    return convertExpression(sl.get("Geometry", None))


def _iconSymbolizer(sl):
    path = os.path.splitext(os.path.basename(sl["image"])[0])
    rotation = _symbolProperty(sl, "rotate")

    paint = {"icon-image": path, "icon-rotate": rotation}
    return {"type": "symbol", "paint": paint}


def _markSymbolizer(sl):
    shape = _symbolProperty(sl, "wellKnownName")
    paint = {}
    if shape.startswith("file://"):
        svgFilename = shape.split("//")[-1]
        name = os.path.splitext(svgFilename)[0]
        paint["icon-image"] = name
        rotation = _symbolProperty(sl, "rotate")
        paint["icon-rotate"] = rotation
        return {"type": "symbol", "paint": paint}
    else:
        size = _symbolProperty(sl, "size")
        opacity = _symbolProperty(sl, "opacity")
        color = _symbolProperty(sl, "color")
        outlineColor = _symbolProperty(sl, "strokeColor")
        outlineWidth = _symbolProperty(sl, "strokeWidth")

        paint["circle-radius"] = ["/", size, 2]
        paint["circle-color"] = color
        paint["circle-opacity"] = opacity
        paint["circle-stroke-width"] = outlineWidth
        paint["circle-stroke-color"] = outlineColor

        return {"type": "circle", "paint": paint}


def _fillSymbolizer(sl):
    opacity = _symbolProperty(sl, "opacity")
    color = sl.get("color", None)
    graphicFill = sl.get("graphicFill", None)
    if graphicFill is not None:
        _warnings.append("Marker fills not supported for Mapbox GL conversion")
        # TODO
    paint = {"fill-opacity": opacity}
    if color is not None:
        paint["fill-color"] = color

    outlineColor = _symbolProperty(sl, "outlineColor")
    return {"type": "fill", "paint": paint}


def _rasterSymbolizer(sl):
    return {"type": "raster"}  # TODO
