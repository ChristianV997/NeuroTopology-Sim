# Reviewed Data-Access Exception Registry

## 1. Overview & Purpose

The **Reviewed Data-Access Exception Registry** (`tools.data_access.exception_registry`) provides a strict, time-bounded, expiring mechanism to track and govern legacy data-access findings while migration to approved bounded acquisition adapters is actively underway in `NeuroTopology-Sim`.

### Core Architectural Invariants
1. **Registry Separation**: The exception registry is kept completely separate from the policy scanner (`tools.data_access.policy_enforcement`). It **never suppresses scanner findings**; every finding remains fully visible in audit reports.
2. **No False Compliance**: An active exception is merely an acknowledged and tracked temporary exemption with an accountable owner and a target migration issue. **The repository is NEVER declared compliant merely because an exception exists.**
3. **Strict Fail-Closed Lifecycle**: Expired, malformed, ownerless, wildcard, or unsafe exceptions fail closed immediately, blocking validation.
4. **Absolute Safety Prohibitions**: Exceptions can never grant permission for dangerous or unconstrained data operations.

---

## 2. Versioned Exception Record Schema (`NeuroTopology.DataAccessReviewedException.v1`)

Each exception record is stored as an individual JSON file under `configs/data_access/reviewed_exceptions/`.

| Field | Type | Requirement | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | **Required** | Must be `NeuroTopology.DataAccessReviewedException.v1`. |
| `exception_id` | `string` | **Required** | Unique identifier (e.g., `EXC-20260911-001`). |
| `exact_file` | `string` | **Required** | Exact relative file path (e.g. `dataset_acquisition/download_eeg.py`). Wildcards (`*`, `?`, `**`, `.`) and directory-wide scopes are strictly rejected. |
| `exact_line` | `integer` | *Conditional* | Exact 1-indexed line number (`> 0`). At least one of `exact_line` or `exact_symbol` is required. |
| `exact_symbol` | `string` | *Conditional* | Exact function, class, or variable symbol name. Wildcards (`*`) are strictly rejected. |
| `rule_identifier` | `string` | **Required** | Exact policy rule being temporarily excepted (e.g., `unconstrained_download`). Wildcards rejected. |
| `owner` | `string` | **Required** | Accountable engineer or team handle. Wildcard or ownerless records (`*`, `all`, `nobody`, `unknown`) are strictly rejected. |
| `reviewer` | `string` | **Required** | Independent reviewer. Self-review (`reviewer == owner`) is strictly prohibited. |
| `justification` | `string` | **Required** | Detailed technical justification explaining why the exception is needed during migration (minimum 10 characters). |
| `migration_issue` | `string` | **Required** | Tracking ticket or PR for remediation (e.g., `GH-331`, `#331`, `https://github.com/...`). |
| `created_date` | `string` | **Required** | ISO 8601 date (`YYYY-MM-DD`). |
| `expiry_date` | `string` | **Required** | ISO 8601 date (`YYYY-MM-DD`). Max lifespan is 90 days. Permanent exceptions (`never`, `null`, `9999`) are strictly rejected. |
| `permitted_behavior` | `list[str]` | **Required** | Non-empty list of specific temporary behaviors allowed during the migration window. |
| `prohibited_behavior` | `list[str]` | **Required** | Explicit declaration of prohibited safety invariants that remain in force. |
| `status` | `string` | **Required** | Evaluated state (`ACTIVE`, `EXPIRED`, `MALFORMED`, `UNSAFE_REJECTED`, `WILDCARD_REJECTED`, `PERMANENT_REJECTED`, `OWNERLESS_REJECTED`, `REVOKED`). |

---

## 3. Strict Fail-Closed Invariants

### 3.1 Wildcard and Scope Rejection
Any exception containing glob patterns (`*`, `?`, `[`, `]`, `**`) in `exact_file`, `exact_symbol`, `rule_identifier`, `owner`, or `reviewer` is rejected with `WILDCARD_FILE`, `WILDCARD_SYMBOL`, or `REPOSITORY_WIDE_SCOPE`.

### 3.2 Permanent and Excessive Lifespan Rejection
- Exceptions with missing or invalid `expiry_date` are rejected with `PERMANENT_EXCEPTION`.
- Exceptions with duration `(expiry_date - created_date) > 90 days` are rejected with `EXCESSIVE_LIFESPAN`.
- Exceptions evaluated after `expiry_date` fail closed with `EXPIRED`.

### 3.3 Mandatory Migration Issue Tracking
Exceptions must explicitly link to a GitHub issue or PR (`#123`, `GH-123`, or URL). Vague placeholders (`TODO`, `someday`, `none`) are rejected with `MISSING_MIGRATION_ISSUE` or `INVALID_MIGRATION_ISSUE`.

### 3.4 Separation of Duties
An engineer cannot approve their own exception (`owner == reviewer` triggers `SELF_REVIEW_PROHIBITED`).

---

## 4. Forbidden Behaviors (Never Permitted)

The validator strictly scans `permitted_behavior` against the forbidden behavior matrix. If any exception attempts to permit any of the following operations, it is immediately rejected with `UNSAFE_BEHAVIOR_PERMITTED`:

1. **`full_dataset_download`**: Bulk dataset cloning, unconstrained multi-subject downloads.
2. **`unbounded_remote_read`**: Infinite streams, reading remote files without byte ranges.
3. **`missing_checksum`**: Bypassing SHA-256 integrity verification or skipping checksum checks.
4. **`output_root_escape`**: Writing outside designated cache roots or path traversal (`..`).
5. **`network_enabled_default`**: Enabling network access implicitly without explicit operator opt-in.
6. **`fabricated_provenance`**: Synthesizing fake manifests or untracked data lineage.

---

## 5. CLI Reference (`scripts/validate_data_access_exceptions.py`)

### 5.1 Basic Validation (Markdown Summary)
```bash
python scripts/validate_data_access_exceptions.py --format markdown
```

### 5.2 Strict Audit for CI (Finite JSON Output)
```bash
python scripts/validate_data_access_exceptions.py \
  --exceptions-dir configs/data_access/reviewed_exceptions \
  --format json \
  --strict
```

### 5.3 Deterministic As-Of Date Validation
```bash
python scripts/validate_data_access_exceptions.py \
  --as-of-date "2026-10-01" \
  --strict
```

---

## 6. Current Exception Inventory

| Exception ID | Target File | Line / Symbol | Rule | Owner | Reviewer | Expiry | Migration Issue |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `EXC-20260911-001` | `dataset_acquisition/download_eeg.py` | Line 34 (`download_file`) | `unconstrained_download` | `antigravity-a` | `codex-d` | `2026-10-11` | [GH-331](https://github.com/ChristianV997/NeuroTopology-Sim/pull/331) |
| `EXC-20260911-002` | `scripts/fetch_real_datasets.py` | Line 28 (`fetch_dataset`) | `unbounded_remote_fetch` | `antigravity-a` | `claude-researcher` | `2026-10-15` | [GH-332](https://github.com/ChristianV997/NeuroTopology-Sim/issues/332) |
