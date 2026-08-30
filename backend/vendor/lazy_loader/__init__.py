"""lazy_loader - minimal implementation for vendored skimage.

Provides lazy importing of submodules and attributes, with graceful
fallback when .pyi stub files are not present.

This is a compact re-implementation of the upstream
``scientific-python/lazy_loader`` package covering the API surface used by
scikit-image: ``attach``, ``attach_stub``, and ``load``.
"""
import ast
import importlib
import os
import sys
import types

__all__ = ["attach", "attach_stub", "load", "register"]


# --------------------------------------------------------------------------
# Lazy module proxy
# --------------------------------------------------------------------------

class _LazyModuleProxy(types.ModuleType):
    """Module proxy that imports the real module on first attribute access."""

    def __init__(self, fullname, error_on_import=False):
        super().__init__(fullname)
        self.__fullname = fullname
        self.__error_on_import = error_on_import
        self.__init_done = False

    def _load(self):
        if not self.__init_done:
            module = importlib.import_module(self.__fullname)
            object.__setattr__(self, "__init_done", True)
            # Copy the real module's dict into this proxy
            for attr in dir(module):
                if not attr.startswith("__"):
                    object.__setattr__(self, attr, getattr(module, attr))
        return self

    def __getattr__(self, name):
        if name in ("__fullname", "__error_on_import", "__init_done",
                    "_load"):
            raise AttributeError(name)
        try:
            module = importlib.import_module(self.__fullname)
            return getattr(module, name)
        except Exception as e:
            if self.__error_on_import:
                raise
            raise AttributeError(
                f"module {self.__fullname!r} has no attribute {name!r}: {e}"
            )

    def __dir__(self):
        return ["attach", "attach_stub", "load", "register"]


def load(fullname, *, error_on_import=False):
    """Return a lazily-loaded module proxy.

    The actual import is deferred until the first attribute access.
    """
    return _LazyModuleProxy(fullname, error_on_import=error_on_import)


# --------------------------------------------------------------------------
# attach() - lazy import of named submodules and attributes
# --------------------------------------------------------------------------

def _attach(parent_package_name, submodules, submod_attrs):
    """Attach lazy loaders to an already-imported parent module."""
    parent_module = sys.modules[parent_package_name]

    submod_attrs = list(submod_attrs.items()) if isinstance(submod_attrs, dict) else submod_attrs

    def __getattr__(name):
        if name in submodules:
            module = importlib.import_module(
                f"{parent_package_name}.{name}"
            )
            setattr(parent_module, name, module)
            return module

        for submod, attrs in submod_attrs:
            if name in attrs:
                submodule = importlib.import_module(
                    f"{parent_package_name}.{submod}"
                )
                value = getattr(submodule, name)
                setattr(parent_module, name, value)
                return value

        raise AttributeError(
            f"module {parent_package_name!r} has no attribute {name!r}"
        )

    def __dir__():
        attrs = set(submodules)
        for _, attrs_list in submod_attrs:
            attrs.update(attrs_list)
        return sorted(attrs)

    all_list = list(__dir__())
    parent_module.__getattr__ = __getattr__
    parent_module.__dir__ = __dir__
    parent_module.__all__ = all_list

    return __getattr__, __dir__, all_list


def attach(package_name, submodules=None, submod_attrs=None):
    """Lazy import submodules and attributes into a parent package."""
    if submodules is None:
        submodules = []
    if submod_attrs is None:
        submod_attrs = {}
    if isinstance(submod_attrs, dict):
        submod_attrs = list(submod_attrs.items())

    return _attach(package_name, submodules, submod_attrs)


# --------------------------------------------------------------------------
# attach_stub() - parse a .pyi stub file for lazy loading
# --------------------------------------------------------------------------

_STUB_IMPORT_RE = None  # kept for backward compat; unused by _parse_stub


def _parse_stub(stub_header):
    """Parse a .pyi stub file to find submodule imports and their attrs.

    Uses the ``ast`` module to robustly handle multi-line parenthesized
    imports (e.g. ``from ._fetchers import (a, b, c)`` spanning many lines).

    Returns (submodules, submod_attrs) where:
      - submodules is a list of submodule names imported via ``from . import X``
      - submod_attrs is a dict {submodule: [attr, ...]} for ``from .submod import a, b``
    """
    submodules = []
    submod_attrs = {}

    try:
        tree = ast.parse(stub_header)
    except SyntaxError:
        return submodules, submod_attrs

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        # Relative import: node.level >= 1
        if node.level < 1:
            continue
        mod = node.module or ""
        names = [alias.name for alias in node.names if alias.name != "*"]
        if not names:
            continue
        if mod == "":
            # "from . import X, Y" -> submodules
            for n in names:
                if n not in submodules:
                    submodules.append(n)
        else:
            # "from .submod import a, b" -> submod_attrs[submod] = [a, b]
            if mod not in submod_attrs:
                submod_attrs[mod] = []
            for n in names:
                if n not in submod_attrs[mod]:
                    submod_attrs[mod].append(n)

    return submodules, submod_attrs


def attach_stub(name, file):
    """Use PEP 562 stubs to load functions from a .pyi file.

    If the .pyi file does not exist, returns empty loaders so that
    ``import skimage`` still succeeds (submodules loaded explicitly by
    other code paths will continue to work).
    """
    pyi = file.replace(".py", ".pyi")
    if not os.path.isfile(pyi):
        # Graceful fallback: no stub file present.
        # Return no-op loaders; the package remains importable and any
        # submodule/attribute accessed directly (e.g.
        # ``from skimage.morphology._skeletonize import thin``) will work
        # because those submodules use regular Python imports.
        def __getattr__(_name):
            raise AttributeError(
                f"module {name!r} has no attribute {_name!r}"
            )

        def __dir__():
            return []

        return __getattr__, __dir__, []

    try:
        with open(pyi, "r", encoding="utf-8") as f:
            stub_header = f.read()
    except Exception:
        stub_header = ""

    submodules, submod_attrs = _parse_stub(stub_header)
    return _attach(name, submodules, submod_attrs)


# --------------------------------------------------------------------------
# register() - IPython extension support (no-op stub)
# --------------------------------------------------------------------------

def register(*args, **kwargs):  # pragma: no cover
    """Placeholder for IPython extension registration."""
    return None
