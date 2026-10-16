# Bounded public-source static packs

`python -m tools.public_repo_harvest.source_pack` creates a deterministic ZIP containing only explicitly selected, safe text files from a local source directory, ZIP archive, or uncompressed TAR archive. It is an extension of the existing `tools/public_repo_harvest/` pipeline, not another candidate registry or intake system. It performs no network requests and never imports, builds, installs, or executes harvested content.

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
    "manual_review_required": true
  }
}
```

Unknown, missing, or conflicting license information remains `reuse_status: blocked`. A license identifier or a `LICENSE` file by itself is not a compatibility decision. The existing license scanner records likely-license metadata as a hint only; it does not fetch or inspect a remote repository. Reuse can be marked only by an explicit human-reviewed compatible record with one consistent identifier, the existing `safe_to_adapt` status, and an affirmative code-copy gate. This classification is not legal advice and does not copy source code into this repository.

## Bounds and exclusions

Defaults are 256 selected/files, 1 MiB per file, 16 MiB total uncompressed source bytes, depth 12, 20,000,000 output bytes, 32,000,000 archive bytes, 1,024 archive entries, and compression ratio 100. Each bound is configurable through `SourcePackLimits` or matching CLI flags. Archive limits cover all archive file entries (selected or not); source-directory count and byte limits cover manifest-selected paths, which are the only paths traversed/read.

The packer rejects traversal and ambiguous/case-colliding paths, absolute/drive/UNC paths, unsafe symlinks and special files, malformed manifests/archives, excessive depth/size/count, encrypted or unsupported ZIP compression, ZIP64/multi-disk archives, high-ratio ZIP entries, and output-path collisions. It supports classic ZIP stored/deflated entries and uncompressed TAR; compressed TAR and self-extracting/prefixed ZIP archives are deliberately unsupported. It writes a new output atomically and refuses to overwrite an existing file or place output inside a source directory.

`.git`/VCS metadata, caches/build outputs, credential-named files, common binary types, non-UTF-8/control-byte content, and files matching conservative secret patterns are excluded. Exclusions are listed by path and reason without copying their bytes into the pack. `content_excluded` is true when safety filters or archive selection omit content; for directory inputs it is also true because unselected paths are not exhaustively enumerated (`unselected_directory_paths_enumerated: false`).

## Determinism and output

The generated archive uses sorted paths, stored (uncompressed) ZIP entries, fixed entry timestamps and permissions, canonical finite JSON, SHA-256 hashes, and no generated wall-clock timestamp. Its embedded `source-pack-manifest.json` records canonical source URL, supplied commit/date, selected paths, per-file size/hash, packer version, exclusions, resource limits, and the license reuse gate. No local absolute paths or source URLs with credentials/query strings are accepted.

Example (all inputs are local):

```bash
python -m tools.public_repo_harvest.source_pack \
  --source /path/to/local/repository \
  --source-manifest /path/to/source-manifest.json \
  --out /path/to/new-source-pack.zip \
  --max-files 256 --max-file-bytes 1048576 --max-total-bytes 16777216 \
  --max-depth 12 --max-output-bytes 20000000
```

Tests use synthetic temporary directories and archives only. They do not download repositories or execute the packed fixture content. The secret detector is heuristic and cannot prove that a pack contains no secrets; review every pack before sharing. The pack is a bounded static inspection artifact, not evidence of scientific validity, software correctness, license compatibility, or source authenticity.
