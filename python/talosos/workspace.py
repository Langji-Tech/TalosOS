"""Workspace + package manifest model for TalosOS."""

from typing import Dict, Iterable, List, Optional

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

WORKSPACE_MARKER = ".talos_ws"
MANIFEST_FILENAME = "package.yaml"

# Directories inside a workspace that never contain packages.
_PRUNE_NAMES = frozenset({
    "build", "install", "logs", ".git", ".idea", "__pycache__",
})

class WorkspaceError(RuntimeError):
    """Raised for invalid workspaces or manifests."""

def find_workspace_root(start: Optional[Path] = None) -> Path:
    """Walk upwards from `start` (or cwd) looking for the .talos_ws marker."""
    env = os.environ.get("TALOSOS_WORKSPACE_ROOT")
    if env:
        root = Path(env).resolve()
        if (root / WORKSPACE_MARKER).is_file():
            return root

    cwd = (start or Path.cwd()).resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / WORKSPACE_MARKER).is_file():
            return parent
    raise WorkspaceError(
        f"no {WORKSPACE_MARKER} marker found from {cwd}. "
        f"Create one with `touch {WORKSPACE_MARKER}` at the workspace root."
    )

def infer_workspace_root(start: Optional[Path] = None) -> Path:
    """Pick a sensible workspace root when no .talos_ws marker exists yet.

    Rules:
      - `<root>/src` (current dir named `src`)          -> root = parent
      - `<root>` with an existing `src/` subdirectory   -> root = cwd
      - `<root>` with no `src/`                         -> root = cwd
    """
    cwd = (start or Path.cwd()).resolve()
    if cwd.name == "src":
        return cwd.parent
    return cwd

def ensure_workspace_root(start: Optional[Path] = None,
                            *,
                            announce: bool = True) -> Path:
    """Return an existing workspace root, or initialize one next to the caller.

    Mirrors the ROS1 `catkin_create_pkg` ergonomics: the user only has to
    `mkdir -p ws/src && cd ws/src` and the tooling figures out the rest.
    """
    try:
        return find_workspace_root(start)
    except WorkspaceError:
        pass

    root = infer_workspace_root(start)
    marker = root / WORKSPACE_MARKER
    marker.touch()
    (root / "src").mkdir(exist_ok=True)
    if announce:
        import sys
        print(f"initialized workspace at {root}", file=sys.stderr)
    return root

@dataclass
class Package:
    name: str
    path: Path
    version: str = "0.0.0"
    description: str = ""
    depends: List[str] = field(default_factory=list)
    executables: List[str] = field(default_factory=list)
    raw: Dict = field(default_factory=dict)

    @property
    def manifest_path(self) -> Path:
        return self.path / MANIFEST_FILENAME

def load_package(manifest_path: Path) -> Package:
    with open(manifest_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise WorkspaceError(f"{manifest_path}: manifest must be a YAML mapping")
    if "name" not in data:
        raise WorkspaceError(f"{manifest_path}: missing required 'name' field")
    return Package(
        name=str(data["name"]),
        path=manifest_path.parent,
        version=str(data.get("version", "0.0.0")),
        description=str(data.get("description", "")),
        depends=[str(x) for x in (data.get("depends") or [])],
        executables=[str(x) for x in (data.get("executables") or [])],
        raw=data,
    )

@dataclass
class Workspace:
    root: Path

    @property
    def src_dir(self) -> Path:
        return self.root / "src"

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def install_dir(self) -> Path:
        return self.root / "install"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    def iter_manifests(self) -> Iterable[Path]:
        # Prefer src/ if it exists; otherwise search the whole workspace.
        roots = [self.src_dir] if self.src_dir.is_dir() else [self.root]
        for base in roots:
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in _PRUNE_NAMES]
                if MANIFEST_FILENAME in filenames:
                    yield Path(dirpath) / MANIFEST_FILENAME

    def find_packages(self):
        pkgs = []  # type: List[Package]
        seen_names = set()  # type: set
        for manifest in self.iter_manifests():
            pkg = load_package(manifest)
            if pkg.name in seen_names:
                raise WorkspaceError(
                    f"duplicate package '{pkg.name}': already seen elsewhere in workspace"
                )
            seen_names.add(pkg.name)
            pkgs.append(pkg)
        return sorted(pkgs, key=lambda p: p.name)

    def find_package(self, name: str) -> Optional[Package]:
        for pkg in self.find_packages():
            if pkg.name == name:
                return pkg
        return None

def load_workspace(start: Optional[Path] = None) -> Workspace:
    return Workspace(root=find_workspace_root(start))

def load_or_init_workspace(start: Optional[Path] = None) -> Workspace:
    """Like `load_workspace`, but auto-initializes a workspace when none exists."""
    return Workspace(root=ensure_workspace_root(start))
