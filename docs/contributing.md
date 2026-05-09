# Contributing

## Governance validation entrypoints

Current governance validation flows are split across three layers:

- `governance/schema.json`: JSON Schema-level structure and conditional requirements (`if/then`) for `claim_type` (`K`/`C` require discriminator, controls, readouts).
- `governance/spec.py`: dataclass models (`HypothesisSpec`, `Discriminator`, `Control`, `Readout`, etc.) used as the in-memory representation.
- `governance/validate.py`: hard semantic governance gates in `validate_spec(...)` plus CLI entrypoint for reproducible validation runs.

## Reproducible command

Run governance validation over `governance/specs/`:

```bash
python -m governance.validate
```

Or run against a specific file/directory:

```bash
python -m governance.validate governance/specs/HYP-20260506-001.yaml
python -m governance.validate governance/specs
```

## Local task runner

Use the make target:

```bash
make validate-governance
```

## CI

CI runs governance validation in a separate fast `governance-validate` job before the matrix test job.

## Expected output

### Pass example

- Each file prints `PASS <path>`
- Final line prints `Validation passed: <N> file(s) checked.`
- Exit code `0`

### Fail example

- Invalid files print `FAIL <path>: <error details>`
- Final line prints `Validation failed: <N> file(s) invalid.`
- Exit code `1`

## Common failure remediation

- **`claim_type` K/C missing discriminator/controls/readouts**
  - Add non-empty `discriminator.description`
  - Ensure at least one `controls` entry
  - Ensure at least one `readouts` entry
- **`claim_type` C missing causal rigor fields**
  - Add at least one `alternatives_considered` item
  - Add non-empty `pass_fail.thresholds`
- **Invalid enum values** (`claim_type`, `layer`, discriminator/data modes)
  - Align values with `governance/schema.json` and `governance/spec.py` comments
- **ID format issues**
  - Use `HYP-YYYYMMDD-NNN` format to satisfy schema pattern.
