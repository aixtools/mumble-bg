"""Shared Murmur ICE slice loading for mumble-bg."""

from __future__ import annotations

from pathlib import Path


SLICE_PATH = Path(__file__).with_name('MumbleServer.ice')


def get_slice_path() -> str:
    """Return the bundled path to the Murmur ICE slice."""
    return str(SLICE_PATH)


def load_ice_module():
    """Load the bundled ICE slice and return the generated bindings module."""
    try:
        import Ice
    except ImportError as exc:
        raise RuntimeError('ZeroC ICE is not installed') from exc

    if not SLICE_PATH.exists():
        raise RuntimeError(f'Bundled ICE slice is missing: {SLICE_PATH}')

    Ice.loadSlice(f"-I{Ice.getSliceDir()} {SLICE_PATH}")

    try:
        import MumbleServer
        return MumbleServer
    except ImportError:
        try:
            import Murmur
            return Murmur
        except ImportError as exc:
            raise RuntimeError('Failed to load the bundled Murmur ICE slice bindings') from exc
