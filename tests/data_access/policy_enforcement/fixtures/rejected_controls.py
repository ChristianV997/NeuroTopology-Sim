from pathlib import Path
import os


def unsafe_cache_fetch(url, output_root, allow_network=True):
    destination = Path(output_root) / ".." / "outside.bin"
    client.download_file("bucket", "key", str(destination))
    return destination


def unsafe_environment(*, network=True):
    return os.getenv("ALLOW_NETWORK", "true") if network else "disabled"
