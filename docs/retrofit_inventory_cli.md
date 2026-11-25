# Retrofit inventory CLI (Phase 5)

This note describes the **Phase 5 Integration** CLI only.

The CLI writes the six Phase 4 report files by calling
[`tools.retrofit_inventory.reporting.build_report_bundle`](../tools/retrofit_inventory/reporting.py).
It does **not** reimplement the scanner, tool-source registry, validators,
or report envelopes.

Inventory is **not scientific evidence**. The CLI never emits a scientific
`PASS`. An empirical artifact label is a heuristic, not a scientific pass.
The K>100 / scientific PASS gate is out of scope.

Report field meanings live in
[`docs/retrofit_inventory_report.md`](retrofit_inventory_report.md).

This draft PR must **not** be merged from Phase 5 alone.

## Usage

From the repository root:

```bash
python scripts/build_retrofit_inventory.py \
  --repo-root . \
  --output-dir artifacts/retrofit_inventory \
  --offline
```

`--offline` is the default. You may omit it. Real outputs belong under
`artifacts/retrofit_inventory/` (gitignored). Do not commit large generated
inventories.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--repo-root` | `.` | Directory to inventory. Must exist and be a directory. |
| `--output-dir` | `<repo-root>/artifacts/retrofit_inventory` | Where the six JSON files are written. |
| `--offline` | on | Stay offline. Only supported mode. |
| `--online` | off | **Refused.** Prints a warning and stays offline. No network. |
| `--generated-at` | unset | Optional ISO-8601 timestamp forwarded to reporting (tests). |

`--offline` cannot be turned off. `offline=True` is always passed to
`build_report_bundle`. `--online` is accepted so a mistaken live flag fails
closed instead of opening a network path.

## Path policy (fail closed)

Exit code **2** before any report write when:

- `--repo-root` is missing, empty, not a directory, or does not exist.
- `--repo-root` or `--output-dir` contains a `..` path segment.
- `--output-dir` does not **resolve under** `--repo-root`.
- An existing parent of `--output-dir` (between the output path and
  `repo-root`) is not a directory.

Relative `--output-dir` values are joined to `repo-root`. Absolute
`--output-dir` values are allowed only when the resolved path stays under
`repo-root`. This CLI does not write outside the inventoried checkout.

Argparse failures (unknown flags, `--help` is not a failure) also use the
stdlib exit code **2**.

## Exit codes

| Code | When |
|---|---|
| `0` | Bundle `status` is `ok`. |
| `1` | Bundle `status` is `incomplete`. |
| `2` | Bundle `status` is `error`, or argparse / path-policy failure. |

Stdout is a short summary only: `status`, `commit`, and the report
filenames written. No secrets, no file contents.

## What this CLI is not

- Not scientific evidence and not a scientific `PASS` / `FAILED` verdict.
- Not a K>100 gate, PCI validation, or topology proof.
- Not launch authority, not a license opinion, not an ontology.
- Not permission to download datasets, call live APIs, or store credentials.

See [`docs/retrofit_inventory_report.md`](retrofit_inventory_report.md) for
the six filenames and envelope fields.

## Merger

Keep this PR draft. Do not merge.
