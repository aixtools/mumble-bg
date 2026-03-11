from pathlib import Path

from bg.ice import get_slice_path


def test_bundled_slice_path_exists():
    assert Path(get_slice_path()).is_file()
