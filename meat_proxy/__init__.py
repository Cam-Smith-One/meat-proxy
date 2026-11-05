"""Meat Proxy: stop being the human copy-paste layer between your AI agents."""
import os

__version__ = "0.2.6"


def overlaps(a: str, b: str) -> bool:
    """True if two absolute paths are the same file or one folder contains the other."""
    a, b = os.path.realpath(a), os.path.realpath(b)
    return a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")
