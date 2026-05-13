# Agent PR Checklists (DS005620)

## P12 label PR

- [ ] Label source column declared
- [ ] No label inference
- [ ] No filename/topology/artifact-derived labels
- [ ] P12-alignment tests run and listed

## P13 target PR

- [ ] Target mapping source declared
- [ ] No target fabrication
- [ ] P12 → P13 compatibility stated
- [ ] P13 tests run and listed

## P11 benchmark PR

- [ ] Benchmark gate behavior declared
- [ ] No unauthorized P11 promotion-gate modification
- [ ] Mock E2E vs real/local impact declared
- [ ] P11 benchmark commands run and listed

## P18 executor/autonomy PR

- [ ] Runtime execution scope declared
- [ ] No automatic real-contract activation
- [ ] No legacy `mt_real` modification unless explicitly approved
- [ ] Runtime-focused tests run and listed

## P19 conversion PR

- [ ] Input/output conversion contract declared
- [ ] Artifact paths and schema expectations listed
- [ ] No implicit scientific claim expansion
- [ ] Conversion validation commands run and listed

## CI/validator PR

- [ ] Workflow/Makefile target impact declared
- [ ] CI command list updated and deterministic
- [ ] No data download requirement introduced
- [ ] Validator tests run and listed

## docs-only PR

- [ ] No runtime or benchmark logic changes
- [ ] No banned claim language
- [ ] Guardrail wording preserved
- [ ] Relevant docs checks/tests run and listed
