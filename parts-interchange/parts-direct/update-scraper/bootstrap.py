import sys
from pathlib import Path


def ensure_singlethreaded_src_path():
    src_path = Path(__file__).resolve().parents[1] / "singlethreaded-scraper" / "src"
    src_path_str = str(src_path)
    if src_path_str not in sys.path:
        sys.path.insert(0, src_path_str)
