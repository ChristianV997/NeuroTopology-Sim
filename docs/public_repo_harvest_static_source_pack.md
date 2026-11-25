# Bounded public-source static packs

`python -m tools.public_repo_harvest.source_pack` creates a deterministic, metadata-only audit ZIP from a local source directory, ZIP archive, or uncompressed TAR archive. It is an extension of the existing `tools/public_repo_harvest/` pipeline, not another candidate registry or intake system. It performs no network requests and never imports, builds, installs, or executes harvested content. **This offline implementation does not emit reusable source bytes.**

## Input manifest

The input manifest is a small UTF-8 JSON object. The canonical GitHub source URL and selected paths are required. Provenance must include a full 40/64-character commit object ID, an explicit `YYYY-MM-DD` access date, or both; a release tag alone is not treated as immutable. The offline packer records these caller-supplied values but cannot verify that local bytes correspond to the asserted remote revision. Paths are exact relative names in a directory or archive; archive prefixes are not guessed or stripped.

```json
{
  "schema_version": "PublicRepoSourceManifest.v1",
  "source_url": "https://github.com/example/project",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "selected_paths": ["README.md", "src/module.py"],
  "license_record": {
    "detected_license": "unknown",
    "license_spdx": "UNKNOWN",
    "license_status": "unknown",
    "compatibility_status": "blocked_license",
    "review_status": "unreviewed",
    "can_copy_code": false,
    "can_copy_docs": false,
    "manual_review_required": true
  }
}
```

Unknown, missing, conflicting, restricted, or caller-declared compatible license information remains blocked. A license identifier, a `LICENSE` file, `review_status: human_reviewed_compatible`, or copy-permission booleans supplied in JSON do not establish review facts. The scanner does not fetch or inspect a remote repository and this package has no authenticated review-evidence provider. All such values are preserved only under `caller_assertions`; normalized review status remains `unreviewed`, effective copy permissions remain false, and `reuse_status` remains `blocked`. The downstream pattern classifier reports `pattern_only_requires_review` for every caller-supplied record; it does not authorize direct copying or an adapted implementation. The output ZIP contains only `source-pack-manifest.json`, has `pack_mode: metadata_only_blocked` and `source_bytes_included: false`, and the CLI exits with status 2. No source payload is retained as quarantine. A future payload-release flow would need a separate trusted review mechanism with provenance; this packer cannot invent a reviewer, authenticate a declaration, or grant legal clearance. A source path with an unrecognized content type remains blocked rather than guessed.

For audit metadata, remaining safe candidate paths are classified by extension: recognized source-code suffixes are code; Markdown, reStructuredText, text, HTML, and common project-guidance files are documentation; Jupyter notebooks are both. Unrecognized types remain `unclassified`. This path-based classification does not inspect or certify license scope. The manifest records `content_categories`, per-path `license_evaluation.content_classification`, caller-asserted permissions separately from effective permissions (always false here), and block reasons; `reusable` is false, and its payload `files` and `selected_paths` arrays remain empty.

## Bounds and exclusions

Defaults are 256 selected/files, 1 MiB per file, 16 MiB total uncompressed source bytes, depth 12, 20,000,000 output bytes, 32,000,000 archive bytes, 1,024 archive entries, and compression ratio 100. Each bound is configurable through `SourcePackLimits` or matching CLI flags. Archive limits cover all archive file entries (selected or not); source-directory count and byte limits cover manifest-selected paths, which are the only paths traversed/read.

The packer rejects traversal and ambiguous/case-colliding paths, absolute/drive/UNC paths, unsafe symlinks and special files, malformed manifests/archives, excessive depth/size/count, encrypted or unsupported ZIP compression, ZIP64/multi-disk archives, high-ratio ZIP entries, and output-path collisions. It supports classic ZIP stored/deflated entries and uncompressed TAR; compressed TAR and self-extracting/prefixed ZIP archives are deliberately unsupported. It writes a new output atomically and refuses to overwrite an existing file or place output inside a source directory.

`.git`/VCS metadata, caches/build outputs, credential-named files, common binary types, non-UTF-8/control-byte content, and files matching conservative secret patterns are excluded. Exclusions are listed by path and reason without copying their bytes into the pack. `content_excluded` is always true because every payload is withheld; filtered paths carry their specific exclusion reason. For directory inputs, unselected paths are not exhaustively enumerated (`unselected_directory_paths_enumerated: false`).

## Determinism and output

The metadata-only archive uses a fixed manifest path, stored ZIP entries, a fixed timestamp and permissions, canonical finite JSON, and no generated wall-clock timestamp. Its embedded manifest records the canonical source URL, supplied commit/date (explicitly marked caller-supplied and unverified), caller-selected paths, content classifications, withheld-payload size, exclusions, resource limits, caller assertions, and the blocked reuse gate. `selected_paths` and `files` describe payloads actually present; both are empty in this mode. No per-file content digest is emitted, so the manifest does not bind a file path to specific bytes. No local absolute paths or source URLs with credentials/query strings are accepted.

Example (all inputs are local):

```bash
python -m tools.public_repo_harvest.source_pack \
  --source /path/to/local/repository \
  --source-manifest /path/to/source-manifest.json \
  --out /path/to/new-source-pack.zip \
  --max-files 256 --max-file-bytes 1048576 --max-total-bytes 16777216 \
  --max-depth 12 --max-output-bytes 20000000
```

Tests use synthetic temporary directories and archives only. They do not download repositories or execute fixture content. The secret detector is heuristic and cannot prove that a local source contains no secrets; the metadata-only archive never includes those source bytes. Review the manifest before sharing. Structural provenance and withheld byte counts are neither source authenticity nor legal approval, and no scientific, software-correctness, or license-compatibility claim is made.
