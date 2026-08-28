"""Make the pure modules importable without Home Assistant installed.

`custom_components/allerte_italia/__init__.py` imports Home Assistant, which the
test environment deliberately does not have: these tests cover the logic that
works without it. Importing `custom_components.allerte_italia.thresholds` would
normally execute that `__init__` first and fail.

The packages are therefore registered by hand, with a `__path__` but no module
body, so Python can find the submodules while the real `__init__` is never run.
Relative imports inside the package (`from ..geo import ...`) keep working.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "custom_components"
PACKAGE = COMPONENTS / "allerte_italia"


def _register(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_register("custom_components", COMPONENTS)
_register("custom_components.allerte_italia", PACKAGE)
_register("custom_components.allerte_italia.sources", PACKAGE / "sources")
