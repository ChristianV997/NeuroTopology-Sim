# DS005620 Evidence-Packet Exporter: Privacy and Scope

The exporter creates engineering evidence-packet files from explicitly supplied
local artifact and metadata roots. It does not download data, execute a solver,
or establish that a dataset or cohort is authorized for use.

## Data minimization

`participants.tsv` identifiers are processed transiently for duplicate checks and
aggregate counts. Raw participant and excluded identifiers are not written to
JSON, Markdown, Notion payloads, command output, or validation messages. The
exporter does not hash or pseudonymize these identifiers. Source-file checksums
are omitted because hashes of low-entropy or guessable inputs are not
anonymization.

Output is limited to aggregate counts, booleans, allowlisted status values, and
fixed error codes. Row-level task/session/run details, arbitrary source text,
identifier lists, source paths, preregistration references, and nested source
claims are omitted. License reporting describes only whether declarations were
supplied and whether their strings agree; it is not a rights determination.
When caller-supplied plans or inventories include identifiers, internal matching
may contribute to an aggregate completeness count. Neither the matching values
nor a row-level match map is exported, and this status is not cohort identity.

The generated files are:

- `evidence_packet.json`
- `evidence_packet.md`
- `notion_import_payload.json`

The CLI prints artifact names and write status, not input or output paths. The
Python API returns only the generated artifact filenames, not the caller's
output directory, so a sensitive directory name is not echoed by the exporter.
For identical local inputs, packet content is deterministic apart from the
intentional `generated_at` export timestamp.

## Interpretation limits

Aggregate count consistency does not establish participant-level matching,
cohort identity, inclusion/exclusion correctness, or provenance authenticity.
Matching license strings do not establish legal permission, data-use rights, or
license applicability. A local metadata file is not made authoritative by being
parsed, checksummed, or placed in this packet. Missing or malformed metadata
remains incomplete; it is not converted to a successful validation.

This exporter does not verify source authenticity, data-use rights, cohort
identity, model correctness, or scientific claims. It cannot establish physical
or biological validity, causation, consciousness, or any other scientific
conclusion. The project posture remains **HOLD / SYNTHETIC_ONLY** unless separate
governance and scientific gates establish otherwise.

## Test-data contract

Tests construct temporary metadata records with explicit synthetic marker
identifiers and synthetic counts. The former checked-in metadata snapshot was
removed because its provenance could not be established within the permitted
inspection boundary. Tests do not read, parse, execute, or use that snapshot.
