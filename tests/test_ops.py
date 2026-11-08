import pytest

from inventor_mcp import constants as C
from inventor_mcp import ops

from .fakes import make_app, make_part


def test_units():
    assert ops.mm_to_cm(25) == 2.5
    assert ops.cm_to_mm(2.5) == 25


def test_resolve_document_by_name_path_and_default():
    a, _ = make_part("A.ipt", r"C:\w\A.ipt")
    b, _ = make_part("B.ipt", r"C:\w\B.ipt")
    app, _ = make_app(a, b)
    assert ops.resolve_document(app) is a
    assert ops.resolve_document(app, "b.ipt") is b
    assert ops.resolve_document(app, "B.ipt") is b
    with pytest.raises(ValueError):
        ops.resolve_document(app, "missing.ipt")


def test_get_parameters():
    doc, _ = make_part()
    app, _ = make_app(doc)
    params = ops.get_parameters(app)
    assert [(p["name"], p["kind"]) for p in params] == [("Length", "user"), ("d0", "model")]
    assert [p["name"] for p in ops.get_parameters(app, include_model=False)] == ["Length"]


def test_set_parameters_updates_and_creates():
    doc, _ = make_part()
    app, _ = make_app(doc)
    changed = ops.set_parameters(app, {"Length": "80 mm"})
    assert changed[0]["action"] == "updated"
    assert doc.ComponentDefinition.Parameters.Item("Length").Expression == "80 mm"
    assert doc.updates == 1

    with pytest.raises(ValueError):
        ops.set_parameters(app, {"Width": "10 mm"})
    changed = ops.set_parameters(app, {"Width": "10 mm"}, create_missing=True)
    assert changed[0]["action"] == "created"


def test_iproperties_roundtrip():
    doc, _ = make_part()
    app, _ = make_app(doc)
    result = ops.set_iproperties(app, {"Part Number": "A-100", "Supplier": "ACME"})
    assert result[0] == {"name": "Part Number", "set": C.PROPSET_DESIGN, "action": "updated"}
    assert result[1]["set"] == C.PROPSET_CUSTOM
    props = ops.get_iproperties(app)
    assert props[C.PROPSET_DESIGN]["Part Number"] == "A-100"
    assert props[C.PROPSET_CUSTOM]["Supplier"] == "ACME"


def test_create_extrusion_converts_units_and_uses_enums():
    doc, log = make_part()
    app, tg_log = make_app(doc)
    ops.create_extrusion(
        app, "rectangle", {"width": 40, "height": 20}, distance=15, operation="cut", direction="negative"
    )
    calls = dict((name, args) for name, args in log)
    assert calls["def.WorkPlanes.Item"] == (C.ORIGIN_PLANES["XY"],)
    assert calls["def.Features.ExtrudeFeatures.CreateExtrudeDefinition"][1] == C.OPERATIONS["cut"]
    assert calls["def.Features.ExtrudeFeatures.CreateExtrudeDefinition().SetDistanceExtent"] == (
        1.5,
        C.DIRECTIONS["negative"],
    )
    points = [args for name, args in tg_log if name == "tg.CreatePoint2d"]
    assert points == [(-2.0, -1.0), (2.0, 1.0)]


def test_cut_without_body_is_rejected():
    doc, _ = make_part(bodies=0)
    app, _ = make_app(doc)
    with pytest.raises(ValueError, match="existing body"):
        ops.create_extrusion(app, "circle", {"diameter": 10}, 5, operation="cut")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"shape": "triangle", "dimensions": {}, "distance": 5},
        {"shape": "circle", "dimensions": {"radius": 5}, "distance": 0},
        {"shape": "circle", "dimensions": {"radius": 5}, "distance": 5, "plane": "AB"},
        {"shape": "polygon", "dimensions": {"points": [[0, 0], [1, 1]]}, "distance": 5},
    ],
)
def test_create_extrusion_validation(kwargs):
    doc, _ = make_part()
    app, _ = make_app(doc)
    with pytest.raises(ValueError):
        ops.create_extrusion(app, **kwargs)


def test_export_rejects_unknown_format():
    doc, _ = make_part()
    app, _ = make_app(doc)
    with pytest.raises(ValueError, match="Unsupported"):
        ops.export_document(app, r"C:\out\x.xyz")


def test_run_script_returns_result_and_errors():
    doc, _ = make_part()
    app, _ = make_app(doc)
    assert "result = 'Part1.ipt'" in ops.run_script(app, "result = doc.DisplayName")
    assert "hi" in ops.run_script(app, "print('hi')")
    assert "ZeroDivisionError" in ops.run_script(app, "1/0")


def test_describe_error_formats_com_errors():
    from inventor_mcp.com import describe_error

    class com_error(Exception):
        pass

    exc = com_error(-2147352567, "Exception occurred.", (0, "Inventor", "Parameter is read-only", None, 0, -2147467259), None)
    assert describe_error(exc) == "Inventor COM error 0x80020009: Parameter is read-only"
    assert describe_error(ValueError("bad")) == "bad"
    assert describe_error(KeyError("x")) == "KeyError: 'x'"
