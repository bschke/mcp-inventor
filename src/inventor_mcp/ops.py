"""Inventor operations. Every function takes the Inventor.Application object.

Units: the Inventor API works internally in centimetres and radians, no matter
what the document displays. All public functions here accept and return
millimetres so that callers never have to think about that.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import traceback
from typing import Any, Iterator

from . import constants as C

MM_PER_CM = 10.0


def mm_to_cm(value: float) -> float:
    return value / MM_PER_CM


def cm_to_mm(value: float) -> float:
    return value * MM_PER_CM


def iter_com(collection: Any) -> Iterator[Any]:
    """Iterate a 1-based Inventor COM collection."""
    for i in range(1, collection.Count + 1):
        yield collection.Item(i)


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------

def doc_type_name(doc: Any) -> str:
    return C.DOC_TYPE_NAMES.get(doc.DocumentType, f"other({doc.DocumentType})")


def describe_document(doc: Any) -> dict:
    return {
        "name": doc.DisplayName,
        "path": doc.FullFileName or None,
        "type": doc_type_name(doc),
        "dirty": bool(doc.Dirty),
    }


def resolve_document(app: Any, document: str | None = None) -> Any:
    """Find an open document by full path or display name; default: active one."""
    if not document:
        doc = app.ActiveDocument
        if doc is None:
            raise ValueError("No document is open in Inventor.")
        return doc
    wanted = document.lower()
    wanted_path = os.path.normcase(os.path.abspath(document)) if os.sep in document or "/" in document else None
    for doc in iter_com(app.Documents):
        full = doc.FullFileName or ""
        if wanted_path and full and os.path.normcase(os.path.abspath(full)) == wanted_path:
            return doc
        if doc.DisplayName.lower() == wanted or os.path.basename(full).lower() == wanted:
            return doc
    raise ValueError(f"Document '{document}' is not open. Use open_document first.")


def get_status(app: Any) -> dict:
    active = app.ActiveDocument
    return {
        "version": app.SoftwareVersion.DisplayVersion,
        "visible_documents": app.Documents.VisibleDocuments.Count,
        "active_document": describe_document(active) if active is not None else None,
    }


def list_documents(app: Any) -> list[dict]:
    return [describe_document(d) for d in iter_com(app.Documents.VisibleDocuments)]


def open_document(app: Any, path: str, visible: bool = True) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return describe_document(app.Documents.Open(path, visible))


def new_document(app: Any, kind: str = "part", template: str | None = None) -> dict:
    try:
        doc_type = C.DOC_TYPES[kind]
    except KeyError:
        raise ValueError(f"kind must be one of {sorted(C.DOC_TYPES)}") from None
    if not template:
        template = app.FileManager.GetTemplateFile(doc_type)
    return describe_document(app.Documents.Add(doc_type, template, True))


def save_document(app: Any, document: str | None = None, path: str | None = None) -> dict:
    doc = resolve_document(app, document)
    if path:
        doc.SaveAs(path, False)
    elif not doc.FullFileName:
        raise ValueError("Document has never been saved; pass a target path.")
    else:
        doc.Save()
    return describe_document(doc)


def close_document(app: Any, document: str | None = None, save: bool = False) -> str:
    doc = resolve_document(app, document)
    name = doc.DisplayName
    if save:
        doc.Save()
    doc.Close(True)  # SkipSave=True: saving was handled explicitly above
    return f"Closed {name}"


EXPORT_FORMATS = {".stp", ".step", ".igs", ".iges", ".stl", ".sat", ".pdf", ".dwg", ".dxf", ".obj", ".jt"}


def export_document(app: Any, path: str, document: str | None = None) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format '{ext}'. Supported: {sorted(EXPORT_FORMATS)}")
    doc = resolve_document(app, document)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc.SaveAs(path, True)  # SaveCopyAs: Inventor picks the translator from the extension
    return f"Exported {doc.DisplayName} to {path}"


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------

def _component_definition(doc: Any) -> Any:
    if doc.DocumentType not in (C.DOC_PART, C.DOC_ASSEMBLY):
        raise ValueError(f"{doc.DisplayName} is a {doc_type_name(doc)}; this needs a part or assembly.")
    return doc.ComponentDefinition


def _part_definition(doc: Any) -> Any:
    if doc.DocumentType != C.DOC_PART:
        raise ValueError(f"{doc.DisplayName} is a {doc_type_name(doc)}; this needs a part (.ipt).")
    return doc.ComponentDefinition


def _describe_parameter(p: Any, kind: str) -> dict:
    return {
        "name": p.Name,
        "kind": kind,
        "expression": p.Expression,
        "units": p.Units,
        "value_internal": p.Value,  # Inventor database units (cm / rad)
        "comment": getattr(p, "Comment", "") or "",
    }


def get_parameters(app: Any, document: str | None = None, include_model: bool = True) -> list[dict]:
    params = _component_definition(resolve_document(app, document)).Parameters
    result = [_describe_parameter(p, "user") for p in iter_com(params.UserParameters)]
    if include_model:
        result += [_describe_parameter(p, "model") for p in iter_com(params.ModelParameters)]
    return result


def set_parameters(
    app: Any,
    values: dict[str, str],
    document: str | None = None,
    create_missing: bool = False,
    units: str = "mm",
) -> list[dict]:
    doc = resolve_document(app, document)
    params = _component_definition(doc).Parameters
    existing = {p.Name: p for p in iter_com(params)}
    changed = []
    for name, expression in values.items():
        expression = str(expression)
        if name in existing:
            existing[name].Expression = expression
            changed.append({"name": name, "expression": expression, "action": "updated"})
        elif create_missing:
            params.UserParameters.AddByExpression(name, expression, units)
            changed.append({"name": name, "expression": expression, "action": "created"})
        else:
            raise ValueError(f"Parameter '{name}' does not exist (set create_missing=true to add it).")
    doc.Update()
    return changed


# --------------------------------------------------------------------------
# iProperties
# --------------------------------------------------------------------------

def get_iproperties(app: Any, document: str | None = None, property_set: str | None = None) -> dict:
    doc = resolve_document(app, document)
    out: dict[str, dict] = {}
    for ps in iter_com(doc.PropertySets):
        if property_set and ps.Name != property_set and ps.DisplayName != property_set:
            continue
        values = {}
        for prop in iter_com(ps):
            try:
                value = prop.Value
            except Exception:
                continue  # some properties (thumbnails) cannot be marshalled
            if isinstance(value, (str, int, float, bool)) or value is None:
                values[prop.Name] = value
            else:
                values[prop.Name] = str(value)
        out[ps.Name] = values
    return out


def set_iproperties(app: Any, values: dict[str, Any], document: str | None = None) -> list[dict]:
    """Set iProperties by name. Unknown names become custom properties."""
    doc = resolve_document(app, document)
    sets = doc.PropertySets
    search_order = [C.PROPSET_DESIGN, C.PROPSET_SUMMARY, C.PROPSET_DOC_SUMMARY, C.PROPSET_CUSTOM]
    result = []
    for name, value in values.items():
        for set_name in search_order:
            ps = sets.Item(set_name)
            prop = next((p for p in iter_com(ps) if p.Name == name or p.DisplayName == name), None)
            if prop is not None:
                prop.Value = value
                result.append({"name": name, "set": set_name, "action": "updated"})
                break
        else:
            sets.Item(C.PROPSET_CUSTOM).Add(value, name)
            result.append({"name": name, "set": C.PROPSET_CUSTOM, "action": "created"})
    return result


# --------------------------------------------------------------------------
# Geometry info
# --------------------------------------------------------------------------

def get_mass_properties(app: Any, document: str | None = None) -> dict:
    mp = _component_definition(resolve_document(app, document)).MassProperties
    com = mp.CenterOfMass
    return {
        "mass_kg": mp.Mass,
        "volume_mm3": mp.Volume * 1000.0,
        "surface_area_mm2": mp.Area * 100.0,
        "center_of_mass_mm": [cm_to_mm(com.X), cm_to_mm(com.Y), cm_to_mm(com.Z)],
    }


def list_features(app: Any, document: str | None = None) -> list[dict]:
    features = _part_definition(resolve_document(app, document)).Features
    out = []
    for f in iter_com(features):
        entry = {"name": f.Name, "suppressed": bool(f.Suppressed)}
        with contextlib.suppress(Exception):
            entry["health"] = int(f.HealthStatus)
        out.append(entry)
    return out


def set_feature_suppressed(app: Any, feature: str, suppressed: bool, document: str | None = None) -> str:
    doc = resolve_document(app, document)
    features = _part_definition(doc).Features
    target = next((f for f in iter_com(features) if f.Name == feature), None)
    if target is None:
        raise ValueError(f"Feature '{feature}' not found.")
    target.Suppressed = suppressed
    doc.Update()
    return f"{feature} {'suppressed' if suppressed else 'unsuppressed'}"


# --------------------------------------------------------------------------
# Modelling
# --------------------------------------------------------------------------

def _sketch_plane(comp_def: Any, plane: str, offset_mm: float) -> Any:
    plane = plane.upper()
    if plane not in C.ORIGIN_PLANES:
        raise ValueError(f"plane must be one of {sorted(C.ORIGIN_PLANES)}")
    base = comp_def.WorkPlanes.Item(C.ORIGIN_PLANES[plane])
    if not offset_mm:
        return base
    wp = comp_def.WorkPlanes.AddByPlaneAndOffset(base, mm_to_cm(offset_mm))
    wp.Visible = False
    return wp


def _draw_profile(sketch: Any, tg: Any, shape: str, dims: dict) -> None:
    def pt(x: float, y: float) -> Any:
        return tg.CreatePoint2d(mm_to_cm(x), mm_to_cm(y))

    cx, cy = float(dims.get("center_x", 0.0)), float(dims.get("center_y", 0.0))
    if shape == "rectangle":
        w, h = float(dims["width"]), float(dims["height"])
        if w <= 0 or h <= 0:
            raise ValueError("width and height must be positive")
        sketch.SketchLines.AddAsTwoPointRectangle(pt(cx - w / 2, cy - h / 2), pt(cx + w / 2, cy + h / 2))
    elif shape == "circle":
        r = float(dims["diameter"]) / 2 if "diameter" in dims else float(dims["radius"])
        if r <= 0:
            raise ValueError("radius/diameter must be positive")
        sketch.SketchCircles.AddByCenterRadius(pt(cx, cy), mm_to_cm(r))
    elif shape == "polygon":
        points = dims["points"]
        if len(points) < 3:
            raise ValueError("polygon needs at least 3 points")
        lines = []
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            start = lines[-1].EndSketchPoint if lines else pt(x1, y1)
            lines.append(sketch.SketchLines.AddByTwoPoints(start, pt(x2, y2)))
        lines.append(sketch.SketchLines.AddByTwoPoints(lines[-1].EndSketchPoint, lines[0].StartSketchPoint))
    else:
        raise ValueError("shape must be 'rectangle', 'circle' or 'polygon'")


def create_extrusion(
    app: Any,
    shape: str,
    dimensions: dict,
    distance: float,
    plane: str = "XY",
    plane_offset: float = 0.0,
    operation: str = "join",
    direction: str = "positive",
    document: str | None = None,
) -> dict:
    """Sketch a closed profile on an origin plane and extrude it. All lengths in mm."""
    if operation not in C.OPERATIONS:
        raise ValueError(f"operation must be one of {sorted(C.OPERATIONS)}")
    if direction not in C.DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(C.DIRECTIONS)}")
    if distance <= 0:
        raise ValueError("distance must be positive; use direction='negative' to flip")

    doc = resolve_document(app, document)
    comp_def = _part_definition(doc)
    if operation in ("cut", "intersect") and comp_def.SurfaceBodies.Count == 0:
        raise ValueError(f"'{operation}' needs an existing body; create one with operation='join' first.")

    tg = app.TransientGeometry
    sketch = comp_def.Sketches.Add(_sketch_plane(comp_def, plane, plane_offset))
    _draw_profile(sketch, tg, shape, dimensions)
    profile = sketch.Profiles.AddForSolid()

    extrudes = comp_def.Features.ExtrudeFeatures
    definition = extrudes.CreateExtrudeDefinition(profile, C.OPERATIONS[operation])
    definition.SetDistanceExtent(mm_to_cm(distance), C.DIRECTIONS[direction])
    feature = extrudes.Add(definition)
    doc.Update()
    return {"feature": feature.Name, "sketch": sketch.Name, "operation": operation}


# --------------------------------------------------------------------------
# Assemblies
# --------------------------------------------------------------------------

def _assembly_definition(doc: Any) -> Any:
    if doc.DocumentType != C.DOC_ASSEMBLY:
        raise ValueError(f"{doc.DisplayName} is a {doc_type_name(doc)}; this needs an assembly (.iam).")
    return doc.ComponentDefinition


def list_occurrences(app: Any, document: str | None = None) -> list[dict]:
    occs = _assembly_definition(resolve_document(app, document)).Occurrences
    out = []
    for occ in iter_com(occs):
        t = occ.Transformation.Translation
        entry = {
            "name": occ.Name,
            "grounded": bool(occ.Grounded),
            "suppressed": bool(occ.Suppressed),
            "visible": bool(occ.Visible),
            "position_mm": [cm_to_mm(t.X), cm_to_mm(t.Y), cm_to_mm(t.Z)],
        }
        with contextlib.suppress(Exception):
            entry["file"] = occ.ReferencedDocumentDescriptor.FullDocumentName
        out.append(entry)
    return out


def add_occurrence(
    app: Any,
    path: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    grounded: bool = False,
    document: str | None = None,
) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    doc = resolve_document(app, document)
    asm = _assembly_definition(doc)
    tg = app.TransientGeometry
    matrix = tg.CreateMatrix()
    matrix.SetTranslation(tg.CreateVector(mm_to_cm(x), mm_to_cm(y), mm_to_cm(z)))
    occ = asm.Occurrences.Add(path, matrix)
    if grounded:
        occ.Grounded = True
    doc.Update()
    return {"name": occ.Name, "position_mm": [x, y, z]}


# --------------------------------------------------------------------------
# View
# --------------------------------------------------------------------------

def capture_view(app: Any, width: int = 1024, height: int = 768, fit: bool = True) -> bytes:
    view = app.ActiveView
    if view is None:
        raise ValueError("No active view; open a document first.")
    if fit:
        view.Fit()
    fd, path = tempfile.mkstemp(suffix=".png", prefix="inventor_mcp_")
    os.close(fd)
    try:
        view.SaveAsBitmap(path, width, height)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


# --------------------------------------------------------------------------
# Script escape hatch
# --------------------------------------------------------------------------

def run_script(app: Any, code: str) -> str:
    """Execute Python against the live Inventor API. Assign to `result` to return a value."""
    namespace: dict[str, Any] = {
        "app": app,
        "tg": app.TransientGeometry,
        "doc": app.ActiveDocument,
        "mm_to_cm": mm_to_cm,
        "cm_to_mm": cm_to_mm,
        "iter_com": iter_com,
        "result": None,
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<inventor_script>", "exec"), namespace)
    except Exception:
        return buf.getvalue() + "\n--- error ---\n" + traceback.format_exc()
    out = buf.getvalue()
    if namespace.get("result") is not None:
        out += ("\n" if out else "") + f"result = {namespace['result']!r}"
    return out or "(no output)"
