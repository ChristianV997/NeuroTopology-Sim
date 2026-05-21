from __future__ import annotations
import os, tempfile, zipfile
from pathlib import Path


def scan_archive(path: Path, extract: bool = False) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        tops = sorted({n.split('/')[0] for n in names if n})
        hist = {}
        for n in names:
            ext = Path(n).suffix.lower() or "<none>"
            hist[ext] = hist.get(ext, 0) + 1
        extracted_to = None
        if extract:
            td = tempfile.mkdtemp(prefix="project_corpus_zip_")
            zf.extractall(td)
            extracted_to = td
    return {"path": str(path), "file_count": len(names), "top_level_folders": tops, "filetype_histogram": hist, "size": os.path.getsize(path), "extracted_to": extracted_to}
