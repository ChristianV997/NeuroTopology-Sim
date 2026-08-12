"""BenchmarkGalleryIndexV1 -- the record of rendering a `BenchmarkGalleryV1`'s
static HTML index. Deterministic, stdlib-only, escaped -- mirrors
`benchmark_packs.renderer`'s own single-pack index renderer, one level
up: this page links to multiple packs' own indexes and HTML report
packs, it does not re-embed their content.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.validation import BenchmarkPackStoreError, scan_text_for_banned_phrases, validate_benchmark_gallery_index

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_VERSION = "benchmark_packs.gallery_renderer v1"
INDEX_FILENAME = "index.html"

_DISCLAIMER = (
    "Research-use / exploratory artifact. This page is a deterministic, static index over multiple "
    "already-governed, verified benchmark packs -- it is not clinical evidence, does not represent a "
    "validated consciousness biomarker, and does not support a diagnostic, treatment, or "
    "spiritual-attainment claim. See Limitations and Blocked interpretations below."
)

_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; max-width: 1080px;
       margin: 0 auto; padding: 1.5rem 1.25rem 3rem; line-height: 1.5; }
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid #8884; padding-bottom: 0.25rem; }
.disclaimer { background: #fff3cd; color: #664d03; border: 1px solid #ffe69c; border-radius: 6px;
              padding: 0.75rem 1rem; margin: 1rem 0; font-size: 0.92rem; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; }
th, td { border: 1px solid #8884; padding: 0.35rem 0.6rem; text-align: left; font-size: 0.92rem; vertical-align: top; }
th { background: #80808014; }
ul { margin: 0.25rem 0 1rem; padding-left: 1.4rem; }
li { margin-bottom: 0.2rem; }
pre { background: #80808014; border: 1px solid #8884; border-radius: 6px; padding: 0.75rem;
      overflow-x: auto; white-space: pre-wrap; word-break: break-word; font-size: 0.85rem; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
.badge-ok { background: #d1e7dd; color: #0a3622; }
.badge-warn { background: #fff3cd; color: #664d03; }
.badge-fail { background: #f8d7da; color: #58151c; }
.badge-muted { background: #80808022; color: inherit; }
.meta { color: #666; font-size: 0.88rem; }
footer { margin-top: 3rem; font-size: 0.82rem; color: #777; border-top: 1px solid #8884; padding-top: 1rem; }
"""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _repo_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def compute_gallery_index_id(*, gallery_id: str, template_version: str = TEMPLATE_VERSION) -> str:
    basis = {"gallery_id": gallery_id, "template_version": template_version}
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class BenchmarkGalleryIndexValidationError(ValueError):
    """Raised when a `BenchmarkGalleryIndexV1` fails structural validation."""


@dataclass
class BenchmarkGalleryIndexV1:
    schema_version: str = _SCHEMA_VERSION
    gallery_index_id: str = ""
    gallery_id: str = ""
    title: str = ""
    output_root: str = ""
    index_html_path: Optional[str] = None
    linked_benchmark_packs: list[str] = field(default_factory=list)
    linked_html_report_packs: list[str] = field(default_factory=list)
    linked_benchmark_indexes: list[str] = field(default_factory=list)
    verification_summary: dict[str, Any] = field(default_factory=dict)
    sections_rendered: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, *, gallery_id: str, _now: Optional[datetime] = None, **kwargs: Any) -> "BenchmarkGalleryIndexV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        gallery_index_id = compute_gallery_index_id(gallery_id=gallery_id)
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            gallery_index_id=gallery_index_id, gallery_id=gallery_id, created_at=ts,
            repo_commit=kwargs.pop("repo_commit", None) or _repo_commit(), **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gallery_index_id": self.gallery_index_id,
            "gallery_id": self.gallery_id,
            "title": self.title,
            "output_root": self.output_root,
            "index_html_path": self.index_html_path,
            "linked_benchmark_packs": list(self.linked_benchmark_packs),
            "linked_html_report_packs": list(self.linked_html_report_packs),
            "linked_benchmark_indexes": list(self.linked_benchmark_indexes),
            "verification_summary": dict(self.verification_summary or {}),
            "sections_rendered": list(self.sections_rendered),
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkGalleryIndexV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            gallery_index_id=d.get("gallery_index_id", ""),
            gallery_id=d.get("gallery_id", ""),
            title=d.get("title", ""),
            output_root=d.get("output_root", ""),
            index_html_path=d.get("index_html_path"),
            linked_benchmark_packs=list(d.get("linked_benchmark_packs") or []),
            linked_html_report_packs=list(d.get("linked_html_report_packs") or []),
            linked_benchmark_indexes=list(d.get("linked_benchmark_indexes") or []),
            verification_summary=dict(d.get("verification_summary") or {}),
            sections_rendered=list(d.get("sections_rendered") or []),
            limitations=list(d.get("limitations") or []),
            blocked_interpretations=list(d.get("blocked_interpretations") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkGalleryIndexV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_gallery_index(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkGalleryIndexValidationError("; ".join(errors))


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return _html.escape(str(value))


def _section(title: str, body: str) -> str:
    return f"<section>\n<h2>{_esc(title)}</h2>\n{body}\n</section>\n"


def _list_or_none(items: list) -> str:
    if not items:
        return "<p class=\"meta\">None.</p>"
    return "<ul>\n" + "\n".join(f"<li>{_esc(item)}</li>" for item in items) + "\n</ul>\n"


def _status_badge(status: str) -> str:
    cls = {"passed": "badge-ok", "passed_with_warnings": "badge-warn", "failed": "badge-fail"}.get(status, "badge-muted")
    return f"<span class=\"badge {cls}\">{_esc(status)}</span>"


def render_gallery_index_html(gallery) -> tuple[str, list[str]]:
    """Pure function: `gallery` (a `BenchmarkGalleryV1`) in,
    `(html_text, sections_rendered)` out. No filesystem access, no
    banned-phrase scan (that happens at write time). Deterministic
    ordering: pack summaries sorted by `pack_name`, then `benchmark_pack_id`."""
    sections_rendered: list[str] = []

    def add(title: str, body: str) -> str:
        sections_rendered.append(title)
        return _section(title, body)

    header = (
        f"<h1>{_esc(gallery.gallery_name or gallery.gallery_id)}</h1>\n"
        f"<p class=\"meta\">gallery_id: <code>{_esc(gallery.gallery_id)}</code> "
        f"&middot; generated: {_esc(gallery.created_at)}</p>\n"
        f"<div class=\"disclaimer\">{_esc(_DISCLAIMER)}</div>\n"
    )

    verification_rows = {
        "packs_verified": len(gallery.verified_pack_ids), "packs_failed": len(gallery.failed_pack_ids),
        "total_packs": len(gallery.pack_summaries) + len(gallery.failed_pack_ids),
    }
    verification_summary = add(
        "Verification summary",
        "<table>\n" + "\n".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in verification_rows.items()) + "\n</table>\n",
    )

    sorted_summaries = sorted(gallery.pack_summaries, key=lambda s: (s.get("pack_name") or "", s.get("benchmark_pack_id") or ""))
    if sorted_summaries:
        rows = []
        for s in sorted_summaries:
            index_link = (
                f"<a href=\"{_esc(s.get('generated_index_path'))}\">index</a>"
                if s.get("generated_index_path") else "<span class=\"meta\">none</span>"
            )
            rows.append(
                "<tr>"
                f"<td>{_esc(s.get('pack_name'))}</td>"
                f"<td>{_esc(s.get('pack_kind'))}</td>"
                f"<td>{_esc(', '.join(sorted(s.get('dataset_ids') or [])))}</td>"
                f"<td>{_esc(', '.join(sorted(s.get('modalities') or [])))}</td>"
                f"<td>{_esc(s.get('report_pack_count'))}</td>"
                f"<td>{_esc(s.get('html_pack_count'))}</td>"
                f"<td>{_status_badge(s.get('verification_status'))}</td>"
                f"<td>{index_link}</td>"
                "</tr>"
            )
        pack_table = (
            "<table>\n<tr><th>pack_name</th><th>pack_kind</th><th>datasets</th><th>modalities</th>"
            "<th>report packs</th><th>HTML packs</th><th>verification</th><th>index</th></tr>\n"
            + "\n".join(rows) + "\n</table>\n"
        )
    else:
        pack_table = "<p class=\"meta\">No verified packs.</p>\n"
    pack_table_section = add("Pack table", pack_table)

    coverage_rows = {
        "datasets": ", ".join(sorted(gallery.dataset_ids)) or "none",
        "modalities": ", ".join(sorted(gallery.modalities)) or "none",
        "input_modes": ", ".join(sorted(gallery.input_modes)) or "none",
    }
    coverage = add(
        "Dataset / modality coverage",
        "<table>\n" + "\n".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in coverage_rows.items()) + "\n</table>\n",
    )

    pack_index_links = [s.get("generated_index_path") for s in sorted_summaries if s.get("generated_index_path")]
    pack_indexes = add("Links to benchmark-pack indexes", _list_or_none([
        f"<a href=\"{_esc(p)}\">{_esc(p)}</a>" for p in pack_index_links
    ]) if pack_index_links else "<p class=\"meta\">None.</p>\n")

    html_links = sorted(gallery.html_index_paths)
    html_report_links = add("Links to HTML report packs", _list_or_none([
        f"<a href=\"{_esc(p)}\">{_esc(p)}</a>" for p in html_links
    ]) if html_links else "<p class=\"meta\">None.</p>\n")

    if gallery.failed_pack_ids:
        failed_section_body = _list_or_none(sorted(gallery.failed_pack_ids))
    else:
        failed_section_body = "<p class=\"meta\">None.</p>\n"
    failed_section = add("Failed / warning packs", failed_section_body)

    limitations = add("Limitations", _list_or_none(gallery.limitations))
    blocked = add("Blocked interpretations", _list_or_none(gallery.blocked_interpretations))

    repro = add("Reproducibility / rebuild notes", (
        "<pre>" + _esc(
            "python -m benchmark_packs.export_gallery scan-and-build --root <benchmark_packs_root> --out <gallery_out>"
        ) + "</pre>\n"
    ))

    manifest_rows = {
        "benchmark_pack_paths": len(gallery.benchmark_pack_paths), "verification_paths": len(gallery.verification_paths),
        "report_pack_paths": len(gallery.report_pack_paths), "html_index_paths": len(gallery.html_index_paths),
    }
    manifest = add(
        "Generated artifact manifest",
        "<table>\n" + "\n".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in manifest_rows.items()) + "\n</table>\n",
    )

    future_work = add("Future work", _list_or_none([
        "Signed benchmark-gallery archives.",
        "PDF export of a gallery.",
        "Scheduled gallery regeneration.",
        "Authenticated hosted gallery API.",
        "Richer cross-pack comparison dashboards.",
    ]))

    body = "\n".join([
        header, verification_summary, pack_table_section, coverage, pack_indexes, html_report_links,
        failed_section, limitations, blocked, repro, manifest, future_work,
    ])

    html_text = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{_esc(gallery.gallery_name or gallery.gallery_id)} -- Benchmark Gallery</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}\n"
        f"<footer>repo_commit: {_esc(gallery.repo_commit)} &middot; schema_version: {_esc(gallery.schema_version)}</footer>\n"
        "</body>\n</html>\n"
    )
    return html_text, sections_rendered


def render_benchmark_gallery_index(gallery, out_dir: Union[str, Path]) -> BenchmarkGalleryIndexV1:
    """Renders `gallery`'s static index to `out_dir/index.html`, scans it
    for banned phrases before writing (refuses to write if any are
    found), and returns the resulting `BenchmarkGalleryIndexV1`."""
    resolved_out = Path(out_dir)
    if not resolved_out.is_absolute():
        resolved_out = _REPO_ROOT / resolved_out
    resolved_out.mkdir(parents=True, exist_ok=True)

    html_text, sections_rendered = render_gallery_index_html(gallery)

    banned_hits = scan_text_for_banned_phrases(html_text)
    if banned_hits:
        raise BenchmarkPackStoreError(f"rendered gallery index contains banned phrase(s), refusing to write: {banned_hits}")

    index_path = resolved_out / INDEX_FILENAME
    index_path.write_text(html_text, encoding="utf-8")

    try:
        relative_index_path = str(index_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        relative_index_path = str(index_path)

    gallery_index = BenchmarkGalleryIndexV1.make(
        gallery_id=gallery.gallery_id, title=gallery.gallery_name or gallery.gallery_id,
        output_root=str(out_dir), index_html_path=relative_index_path,
        linked_benchmark_packs=list(gallery.benchmark_pack_paths),
        linked_html_report_packs=list(gallery.html_index_paths),
        linked_benchmark_indexes=[
            s.get("generated_index_path") for s in gallery.pack_summaries if s.get("generated_index_path")
        ],
        verification_summary={
            "verified": len(gallery.verified_pack_ids), "failed": len(gallery.failed_pack_ids),
        },
        sections_rendered=sections_rendered, limitations=list(gallery.limitations),
        blocked_interpretations=list(gallery.blocked_interpretations),
    )
    gallery_index.validate_or_raise()
    return gallery_index
