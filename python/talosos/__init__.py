"""TalosOS Python utilities.

This package currently ships the `talos` command-line interface. Runtime
bindings for Node/Publisher/Subscription (pybind11-powered) land in a later
phase; importing this package today does not require any native extension.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
