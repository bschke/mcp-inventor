"""Minimal stand-ins for Inventor COM objects (1-based collections etc.)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from inventor_mcp import constants as C


class Coll:
    def __init__(self, items=None):
        self.items = list(items or [])

    @property
    def Count(self):
        return len(self.items)

    def Item(self, key):
        if isinstance(key, int):
            return self.items[key - 1]
        for it in self.items:
            if getattr(it, "Name", None) == key:
                return it
        raise KeyError(key)


class Param(SimpleNamespace):
    pass


class UserParams(Coll):
    def __init__(self, items, all_params):
        super().__init__(items)
        self.all = all_params

    def AddByExpression(self, name, expr, units):
        p = Param(Name=name, Expression=expr, Units=units, Value=0.0, Comment="")
        self.items.append(p)
        self.all.items.append(p)
        return p


class Prop(SimpleNamespace):
    pass


class PropSet(Coll):
    def __init__(self, name, props):
        super().__init__(props)
        self.Name = name
        self.DisplayName = name

    def Add(self, value, name):
        self.items.append(Prop(Name=name, DisplayName=name, Value=value))


class Recorder:
    """Records method calls; returns a new Recorder for each call."""

    def __init__(self, name="obj", log=None):
        self._name = name
        self._log = log if log is not None else []

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        child = Recorder(f"{self._name}.{attr}", self._log)
        object.__setattr__(self, attr, child)
        return child

    def __call__(self, *args):
        self._log.append((self._name, args))
        return Recorder(f"{self._name}()", self._log)


def make_part(name="Part1.ipt", path=r"C:\work\Part1.ipt", bodies=1):
    params_all = Coll()
    d0 = Param(Name="d0", Expression="10 mm", Units="mm", Value=1.0, Comment="")
    length = Param(Name="Length", Expression="50 mm", Units="mm", Value=5.0, Comment="")
    params_all.items += [d0, length]
    params = SimpleNamespace(
        UserParameters=UserParams([length], params_all),
        ModelParameters=Coll([d0]),
    )
    log: list = []
    comp_def = Recorder("def", log)
    object.__setattr__(comp_def, "Parameters", _ParamsColl(params_all, params))
    object.__setattr__(comp_def, "SurfaceBodies", Coll([object()] * bodies))
    propsets = Coll(
        [
            PropSet(C.PROPSET_DESIGN, [Prop(Name="Part Number", DisplayName="Part Number", Value="P1")]),
            PropSet(C.PROPSET_SUMMARY, [Prop(Name="Title", DisplayName="Title", Value="")]),
            PropSet(C.PROPSET_DOC_SUMMARY, []),
            PropSet(C.PROPSET_CUSTOM, []),
        ]
    )
    doc = SimpleNamespace(
        DisplayName=name,
        FullFileName=path,
        DocumentType=C.DOC_PART,
        Dirty=False,
        ComponentDefinition=comp_def,
        PropertySets=propsets,
        updates=0,
    )
    doc.Update = lambda: setattr(doc, "updates", doc.updates + 1)
    return doc, log


class _ParamsColl(Coll):
    def __init__(self, all_params: Coll, ns: Any):
        super().__init__(all_params.items)
        self._all = all_params
        self.UserParameters = ns.UserParameters
        self.ModelParameters = ns.ModelParameters

    @property
    def Count(self):
        return len(self._all.items)

    def Item(self, key):
        self.items = self._all.items
        return super().Item(key)


def make_app(*docs):
    log: list = []
    app = SimpleNamespace(
        Documents=Coll(docs),
        ActiveDocument=docs[0] if docs else None,
        TransientGeometry=Recorder("tg", log),
    )
    return app, log
