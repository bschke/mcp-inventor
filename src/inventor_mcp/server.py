"""MCP tool definitions for Autodesk Inventor."""

from __future__ import annotations

import os
from typing import Any, Literal

try:  # MCP Python SDK >= 2.0
    from mcp.server.mcpserver import Image
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]
    from mcp.server.fastmcp import Image  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]

from . import ops
from .com import InventorSession, describe_error

INSTRUCTIONS = """\
Controls a running Autodesk Inventor instance on this Windows machine.
All lengths are in millimetres. Parameter expressions use Inventor syntax and
should carry units, e.g. "25 mm" or "d0 * 2". Most tools act on the active
document unless `document` (display name or full path) is given.
Call capture_view after modelling to check the result visually.
"""

mcp = _Server("inventor", instructions=INSTRUCTIONS)

ALLOW_SCRIPTS = os.environ.get("INVENTOR_MCP_ALLOW_SCRIPTS", "0") == "1"


class _Session:
    """Wraps InventorSession so every failure reaches the model with its message."""

    def __init__(self, inner: InventorSession) -> None:
        self.inner = inner

    async def call(self, fn):
        try:
            return await self.inner.call(fn)
        except Exception as exc:
            raise ToolError(describe_error(exc)) from exc


session = _Session(InventorSession())

DocKind = Literal["part", "assembly", "drawing", "presentation"]


# -- documents ---------------------------------------------------------------

@mcp.tool()
async def get_status() -> dict:
    """Inventor version and the currently active document."""
    return await session.call(ops.get_status)


@mcp.tool()
async def list_documents() -> list[dict]:
    """List all documents open in Inventor (visible ones only)."""
    return await session.call(ops.list_documents)


@mcp.tool()
async def open_document(path: str, visible: bool = True) -> dict:
    """Open an .ipt, .iam, .idw or .dwg file."""
    return await session.call(lambda app: ops.open_document(app, path, visible))


@mcp.tool()
async def new_document(kind: DocKind = "part", template: str | None = None) -> dict:
    """Create a new document from the default (or a given) template."""
    return await session.call(lambda app: ops.new_document(app, kind, template))


@mcp.tool()
async def save_document(document: str | None = None, path: str | None = None) -> dict:
    """Save a document. Pass `path` to Save As (required for never-saved documents)."""
    return await session.call(lambda app: ops.save_document(app, document, path))


@mcp.tool()
async def close_document(document: str | None = None, save: bool = False) -> str:
    """Close a document. Unsaved changes are discarded unless save=true."""
    return await session.call(lambda app: ops.close_document(app, document, save))


@mcp.tool()
async def export_document(path: str, document: str | None = None) -> str:
    """Export a copy. Format follows the extension: .step/.stp, .iges/.igs, .stl, .sat,
    .obj, .jt (parts/assemblies) or .pdf, .dwg, .dxf (drawings)."""
    return await session.call(lambda app: ops.export_document(app, path, document))


# -- parameters & iProperties -----------------------------------------------

@mcp.tool()
async def get_parameters(document: str | None = None, include_model: bool = True) -> list[dict]:
    """List user parameters and (optionally) model parameters d0, d1, ..."""
    return await session.call(lambda app: ops.get_parameters(app, document, include_model))


@mcp.tool()
async def set_parameters(
    values: dict[str, str],
    document: str | None = None,
    create_missing: bool = False,
    units: str = "mm",
) -> list[dict]:
    """Set parameter expressions, e.g. {"Length": "120 mm", "d3": "Length / 2"}.
    The model is updated afterwards. create_missing adds new user parameters in `units`."""
    return await session.call(
        lambda app: ops.set_parameters(app, values, document, create_missing, units)
    )


@mcp.tool()
async def get_iproperties(document: str | None = None, property_set: str | None = None) -> dict:
    """Read iProperties (Part Number, Description, Material, custom ones, ...)."""
    return await session.call(lambda app: ops.get_iproperties(app, document, property_set))


@mcp.tool()
async def set_iproperties(values: dict[str, Any], document: str | None = None) -> list[dict]:
    """Set iProperties by name, e.g. {"Part Number": "A-100", "Description": "Bracket"}.
    Names not found in the standard sets are created as custom properties."""
    return await session.call(lambda app: ops.set_iproperties(app, values, document))


# -- part modelling ----------------------------------------------------------

@mcp.tool()
async def create_extrusion(
    shape: Literal["rectangle", "circle", "polygon"],
    dimensions: dict[str, Any],
    distance: float,
    plane: Literal["XY", "XZ", "YZ"] = "XY",
    plane_offset: float = 0.0,
    operation: Literal["join", "cut", "intersect", "new_body"] = "join",
    direction: Literal["positive", "negative", "symmetric"] = "positive",
    document: str | None = None,
) -> dict:
    """Sketch a closed profile on an origin plane and extrude it (all values in mm).

    dimensions by shape:
      rectangle: {"width", "height", optional "center_x", "center_y"}
      circle:    {"diameter" or "radius", optional "center_x", "center_y"}
      polygon:   {"points": [[x, y], ...]}  (closed automatically)
    plane_offset shifts the sketch plane along its normal.
    """
    return await session.call(
        lambda app: ops.create_extrusion(
            app, shape, dimensions, distance, plane, plane_offset, operation, direction, document
        )
    )


@mcp.tool()
async def list_features(document: str | None = None) -> list[dict]:
    """List the features of a part in browser order."""
    return await session.call(lambda app: ops.list_features(app, document))


@mcp.tool()
async def set_feature_suppressed(feature: str, suppressed: bool = True, document: str | None = None) -> str:
    """Suppress or unsuppress a part feature by name."""
    return await session.call(lambda app: ops.set_feature_suppressed(app, feature, suppressed, document))


@mcp.tool()
async def get_mass_properties(document: str | None = None) -> dict:
    """Mass, volume, surface area and centre of mass of a part or assembly."""
    return await session.call(lambda app: ops.get_mass_properties(app, document))


# -- assemblies ----------------------------------------------------------------

@mcp.tool()
async def list_occurrences(document: str | None = None) -> list[dict]:
    """List the top-level components of an assembly."""
    return await session.call(lambda app: ops.list_occurrences(app, document))


@mcp.tool()
async def add_occurrence(
    path: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    grounded: bool = False,
    document: str | None = None,
) -> dict:
    """Place a part/assembly file into the assembly at position (x, y, z) in mm."""
    return await session.call(lambda app: ops.add_occurrence(app, path, x, y, z, grounded, document))


# -- view ----------------------------------------------------------------------

@mcp.tool()
async def capture_view(width: int = 1024, height: int = 768, fit: bool = True) -> Image:
    """Screenshot of the active Inventor view as PNG."""
    data = await session.call(lambda app: ops.capture_view(app, width, height, fit))
    return Image(data=data, format="png")


# -- scripting (opt-in) ----------------------------------------------------------

if ALLOW_SCRIPTS:

    @mcp.tool()
    async def run_script(code: str) -> str:
        """Run Python against the live Inventor COM API for anything the other tools
        do not cover. Available names: app (Inventor.Application), doc (active
        document), tg (TransientGeometry), iter_com(collection), mm_to_cm, cm_to_mm.
        Remember the API uses cm and radians. Assign to `result` to return a value;
        print() output is returned as well."""
        return await session.call(lambda app: ops.run_script(app, code))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
