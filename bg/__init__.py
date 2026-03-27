"""Background runtime package for mumble-bg."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("mumble-bg")
except PackageNotFoundError:
    __version__ = "unknown"
