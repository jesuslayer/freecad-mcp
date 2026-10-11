"""Code filter for execute_code (hardened fork)."""

from pathlib import Path
import sys

import pytest

ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))

from rpc_server.code_policy import check_code, restricted_builtins  # noqa: E402


ALLOWED = [
    "import FreeCAD\ndoc = FreeCAD.newDocument('Doc')",
    "import Part, math\nbox = Part.makeBox(10, 20, math.pi)",
    "from FreeCAD import Vector\nv = Vector(1, 2, 3)",
    "from math import *\nx = sqrt(2)",
    "import numpy as np\na = np.linspace(0, 1, 5)",
    "class Plate:\n    def __init__(self, w):\n        self.w = w\np = Plate(3)",
    "length = getattr(obj, 'Length', 0)",
    "print('done')",
    "for i in range(3):\n    pass",
]

BLOCKED = [
    ("import os", "import of 'os'"),
    ("import subprocess", "import of 'subprocess'"),
    ("from os import system", "import from 'os'"),
    ("from . import rpc_server", "import from '.'"),
    ("__import__('os')", "'__import__'"),
    ("open('secret.txt').read()", "'open'"),
    ("eval('1+1')", "'eval'"),
    ("exec('x=1')", "'exec'"),
    ("compile('1', 'f', 'eval')", "'compile'"),
    ("globals()['x'] = 1", "'globals'"),
    ("vars()", "'vars'"),
    ("().__class__.__bases__[0].__subclasses__()", "'__subclasses__'"),
    ("f.__globals__", "'__globals__'"),
    ("__builtins__", "'__builtins__'"),
    ("getattr(x, '__class__')", "'__class__'"),
    ("getattr(x, name)", "literal attribute name"),
    ("import Draft\nDraft.os.system('calc')", "attribute 'system'"),
    ("import Draft\nmod = Draft.os", "attribute 'os'"),
    ("import FreeCAD\nFreeCAD.sys", "'sys'"),
    ("'{0.__class__}'.format(1)", "'__'"),
    ("from FreeCAD import os", "'os'"),
]


@pytest.mark.parametrize("code", ALLOWED)
def test_modelling_code_passes(code: str) -> None:
    assert check_code(code) is None


@pytest.mark.parametrize(("code", "reason"), BLOCKED)
def test_dangerous_code_is_refused(code: str, reason: str) -> None:
    problem = check_code(code)
    assert problem is not None
    assert reason in problem
    assert problem.startswith("line ")


def test_syntax_errors_are_reported_without_running() -> None:
    assert "syntax error" in check_code("def (")


def test_runtime_builtins_drop_dangerous_functions() -> None:
    safe = restricted_builtins()
    for name in ("open", "eval", "exec", "compile", "globals", "input"):
        assert name not in safe
    assert "print" in safe and "range" in safe and "__build_class__" in safe


def test_runtime_import_guard() -> None:
    namespace = {"__builtins__": restricted_builtins()}
    exec("import math\nr = math.sqrt(4)", namespace)
    assert namespace["r"] == 2
    with pytest.raises(ImportError, match="not allowed"):
        exec("import os", {"__builtins__": restricted_builtins()})
    with pytest.raises(NameError):
        exec("open('x')", {"__builtins__": restricted_builtins()})
