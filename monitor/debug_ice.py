from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from monitor.services import ice_client
    except Exception as exc:
        print("Failed to import monitor.services.ice_client:", exc)
        return 1

    print("sys.path (first 10):")
    for entry in sys.path[:10]:
        print(" ", entry)

    try:
        import importlib.util

        spec = importlib.util.find_spec("monitor.ice.MumbleServer_ice")
        print("spec monitor.ice.MumbleServer_ice:", spec)
        if spec and spec.origin:
            print("origin:", spec.origin)
            print("exists:", Path(spec.origin).exists())
    except Exception as exc:
        print("spec check failed:", exc)

    try:
        import MumbleServer_ice  # type: ignore

        print("Imported MumbleServer_ice:", MumbleServer_ice)
    except Exception as exc:
        print("Import MumbleServer_ice failed:", exc)

    try:
        import MumbleServer  # type: ignore

        print("Imported MumbleServer:", MumbleServer)
    except Exception as exc:
        print("Import MumbleServer failed:", exc)

    print("Candidate ICE paths:")
    try:
        for path in ice_client._candidate_ice_module_paths():
            print(" ", path, "exists:", Path(path).exists())
            if Path(path).is_dir():
                ms_ice = Path(path) / "MumbleServer_ice.py"
                ms_pkg = Path(path) / "MumbleServer"
                print("    MumbleServer_ice.py:", ms_ice.exists())
                print("    MumbleServer pkg:", ms_pkg.exists())
    except Exception as exc:
        print("candidate paths failed:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
