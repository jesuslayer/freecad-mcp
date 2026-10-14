"""Limits on code run by execute_code / execute_code_async (hardened fork).

Two layers, both active while the ``code_filter`` setting is true (default):

1. ``check_code`` parses the script and refuses imports outside
   ``ALLOWED_MODULES``, dangerous builtins, dunder attribute access and
   attributes named after system modules (e.g. ``Draft.os``).
2. ``restricted_builtins`` is the ``__builtins__`` the script runs with: the
   dangerous builtins are removed and ``__import__`` refuses system modules
   (``RUNTIME_BLOCKED_MODULES``) at run time. It is a denylist, not the
   allowlist above, because FreeCAD's C++ core imports its own modules (e.g.
   ``PartGui`` from ``doc.addObject("Part::Box")``) through the builtins of
   the running script.

This is defense in depth, not a sandbox. Python offers many introspection
paths and FreeCAD's own APIs can read and write files (``Part.read``,
``Shape.exportStep``, ``doc.saveAs``...). Keep manual approval of
execute_code in your MCP client; the filter only narrows what slips through.
"""

import ast
import builtins
from typing import Any

ALLOWED_MODULES = frozenset({
    # FreeCAD workbenches used for modelling
    "FreeCAD", "FreeCADGui", "Part", "PartDesign", "Sketcher", "Draft",
    "DraftGeomUtils", "DraftVecUtils", "Mesh", "MeshPart", "Fem", "ObjectsFem",
    "BOPTools", "CompoundTools", "Spreadsheet",
    # Pure computation
    "math", "cmath", "random", "itertools", "functools", "collections",
    "statistics", "decimal", "fractions", "numbers", "time", "numpy",
})

BLOCKED_BUILTINS = frozenset({
    "open", "exec", "eval", "compile", "__import__", "globals", "locals",
    "vars", "breakpoint", "input", "help", "exit", "quit", "memoryview",
    "__loader__", "__spec__",
})

# Attribute names that reach the OS when exposed by an allowed module.
BLOCKED_ATTRIBUTES = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "ctypes", "importlib",
    "pickle", "marshal", "builtins", "pathlib", "io", "shlex", "runpy",
    "multiprocessing", "threading", "signal", "tempfile", "glob", "urllib",
    "http", "ftplib", "smtplib", "webbrowser", "code", "codeop", "inspect",
    "system", "popen", "spawnv", "execv", "startfile",
    # More of os's process API, in case an alias of os is ever exposed.
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnve", "spawnvp",
    "spawnvpe", "execl", "execle", "execlp", "execlpe", "execve", "execvp",
    "execvpe", "posix_spawn", "posix_spawnp", "fork", "forkpty",
    # Runs a string of Python in FreeCAD's own interpreter, outside the
    # script's restricted builtins.
    "doCommand", "doCommandGui", "doCommandEval", "doCommandSkip",
    # Run macros, commands or imports in FreeCAD's own interpreter.
    "loadFile", "runCommand", "addModule",
    # numpy paths to native code or pickle.
    "ctypeslib", "load", "read_array", "extbuild", "f2py", "distutils",
})

_ATTR_FUNCTIONS = frozenset({"getattr", "setattr", "delattr", "hasattr"})

# Modules the runtime __import__ guard refuses, whoever asks for them.
RUNTIME_BLOCKED_MODULES = frozenset({
    "os", "nt", "posix", "sys", "subprocess", "shutil", "socket", "ssl",
    "ctypes", "importlib", "pickle", "marshal", "builtins", "pathlib", "io",
    "shlex", "runpy", "multiprocessing", "threading", "_thread", "signal",
    "tempfile", "glob", "urllib", "http", "ftplib", "smtplib", "webbrowser",
    "code", "codeop", "inspect", "winreg", "_winapi", "msvcrt", "asyncio",
    "zipimport", "pty",
})


def _top_level(name: str) -> str:
    return name.split(".", 1)[0]


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


class _Checker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.problem: str | None = None

    def _fail(self, node: ast.AST, reason: str) -> None:
        if self.problem is None:
            self.problem = f"line {getattr(node, 'lineno', '?')}: {reason}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _top_level(alias.name) not in ALLOWED_MODULES:
                self._fail(node, f"import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module or _top_level(node.module) not in ALLOWED_MODULES:
            self._fail(node, f"import from '{node.module or '.'}' is not allowed")
        for alias in node.names:
            if alias.name in BLOCKED_ATTRIBUTES or alias.name.startswith("_"):
                self._fail(node, f"importing '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in BLOCKED_BUILTINS or _is_dunder(node.id):
            self._fail(node, f"use of '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_dunder(node.attr):
            self._fail(node, f"access to '{node.attr}' is not allowed")
        elif node.attr.startswith("_"):
            # Stdlib modules keep private aliases of system modules
            # (random._os, collections._sys); the name check below cannot
            # see them, and no modelling code needs a private attribute.
            self._fail(node, f"access to private attribute '{node.attr}' is not allowed")
        elif node.attr in BLOCKED_ATTRIBUTES:
            self._fail(node, f"access to attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in _ATTR_FUNCTIONS:
            name = node.args[1] if len(node.args) > 1 else None
            if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
                self._fail(node, f"{func.id}() needs a literal attribute name")
            elif name.value.startswith("_") or name.value in BLOCKED_ATTRIBUTES:
                self._fail(node, f"{func.id}() on '{name.value}' is not allowed")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # Blocks "{0.__class__}".format(x)-style attribute walks.
        if isinstance(node.value, str) and "__" in node.value:
            self._fail(node, "strings containing '__' are not allowed")
        self.generic_visit(node)


def check_code(code: str) -> str | None:
    """Return why ``code`` is refused, or None when it passes the filter."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"line {e.lineno}: syntax error: {e.msg}"
    checker = _Checker()
    checker.visit(tree)
    return checker.problem


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or _top_level(name) in RUNTIME_BLOCKED_MODULES:
        raise ImportError(f"import of '{name}' is not allowed by the code filter")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _build_restricted_builtins() -> dict[str, Any]:
    safe = {k: v for k, v in vars(builtins).items() if k not in BLOCKED_BUILTINS}
    safe["__import__"] = _guarded_import
    return safe


_RESTRICTED_BUILTINS = _build_restricted_builtins()


def restricted_builtins() -> dict[str, Any]:
    return _RESTRICTED_BUILTINS
