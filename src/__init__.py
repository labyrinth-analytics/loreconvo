from importlib.metadata import version as _v, PackageNotFoundError
try:
    __version__ = _v("loreconvo")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

try:
    from .anthropic_bridge import LoreConvoMemoryBackend
    __all__ = ["LoreConvoMemoryBackend"]
except ImportError:
    __all__ = []
