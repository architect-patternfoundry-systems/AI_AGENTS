"""Pytest configuration — make contract modules importable as top-level."""
import sys
from pathlib import Path

# Insert the package directory itself so modules can be imported by name
# (the directory name has a hyphen and is not a valid Python package name).
_root = str(Path(__file__).parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
