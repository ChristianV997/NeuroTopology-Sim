# Agents C / D — location status (Intrinsic Existence / Batch 2)

**Date:** 2026-10-30  
**Verdict:** Cloud transcripts for Agents C and D were **not obtained**. No environment-listed chat is literally named “Agent C” or “Agent D.” Candidate bcIds recovered from PR footers are **not accessible** to `batch-fetch-details` in this run.

**Known accessible sibling chats:**
| Label | bcId | Status in this env |
|---|---|---|
| Agent A | `bc-55eeb0ea-9451-46f9-91ca-bd666b6396c3` | Listed (desktop); transcript previously fetched |
| Agent B | `bc-4712080c-4905-41a3-90bf-f71b0a4664cc` | Listed (desktop); transcript previously fetched |

---

## 1. Search performed

### cursor-cloud `list-cloud-agents`
| Filter | Result |
|---|---|
| `includeArchived=true`, limit 200 | **54** agents; only desktop names **Agent A** / **Agent B** |
| `sources=["desktop"]` + archived | **2** — A and B only |
| `didCreatePullRequest=true` + archived | **3** — A, B, environment setup |
| `sources=["web","scm","cli","slack","api","sdk","automations","local"]` | **0** |
| `statuses=["ARCHIVED","EXPIRED","ERROR","IDLE"]` + archived | **52** (internal Bugbots/reviews + A/B/env); no Agent C/D names |
| Keyword match on name/branch (Agent C/D, Cursor C, Codex D, Antigravity C, Pigozzi, ΦID, interventional, sensitivity, serial merge) | Hits only this finder chat + unrelated Bugbot “spherical CSD” reviews |
| `offset=50`, `didMakeCodeChanges=true` | Empty page; no additional named C/D |

### cursor-cloud `batch-fetch-details` (includeTranscripts)
| bcId | Provenance | Result |
|---|---|---|
| `bc-5f3561a4-f81f-4804-93e5-34744d0fd374` | PR **#378** footer (`batch2/cursor-c-mne-csd-adapter`); also in Agent A transcript | **Not found / not accessible** |
| `bc-a4658b9c-94e2-4df8-8fb1-242f8d1b6c11` | PR **#452** footer (`followup/batch2-cursor-d-dmd-production-…`); also in Agent B transcript | **Not found / not accessible** |

No other C/D bcIds appear in `AGENT_A_DIGEST.md` / `AGENT_B_DIGEST.md` beyond A/B themselves and the inaccessible PR-footer IDs above.

### Filesystem
| Query | Result |
|---|---|
| `HANDOFF_AGENT_C.md` / `HANDOFF_AGENT_D.md` under `/opt/cursor/artifacts`, `/tmp`, `/workspace` | **No live files** named that way |
| Agent B transcript diff | Full text of `/opt/cursor/artifacts/batch2_agent_b_alpha_estimators/docs/HANDOFF_AGENT_C.md` recovered → `HANDOFF_AGENT_C_RECOVERED.md` |
| `HANDOFF_AGENT_B.md` | Present under batch2 shared-fixture / generative-alpha artifacts |
| Codex D merge packets | `/opt/cursor/artifacts/codex-d-merge-handoff.md`, `/opt/cursor/artifacts/371-codex-d-handoff.md` |
| GitHub code search `HANDOFF_AGENT_C` | **0** hits in repo |

---

## 2. Who “C” and “D” were (multiple lanes; name collisions)

Batch 2 / Intrinsic Existence used letter labels across **vendors**. Digests and PRs do **not** map 1:1 to a single cloud chat named Agent C/D.

### Cursor Agent C (science / Intrinsic Existence — from A/B digests)

**Assigned work (not verified as done in an accessible chat):**
1. **Interventional Pigozzi / macro-causal benchmarks** — Agent B explicitly deferred this lane: high ΦID Syn ≠ interventional macro closure / agency / viability / experience / dissipation; “Cursor C owns interventional benchmarks.”
2. **Statistical simulations** consuming Agent B’s estimator panel — handoff document (recovered) targeted calibration curves, winding Type I, PLV–PLI dissociation, sign accuracy, abstention sensitivity. Path was meant to be `batch2_agent_b_alpha_estimators/docs/HANDOFF_AGENT_C.md` (artifact tree **no longer on disk**).
3. Agent A open thread #8 also lists an **interventional macro do-control falsifier** as unfinished Pigozzi follow-up (alongside B’s sensitivity grid).

**Science content available without C’s transcript** (from A/B + Pigozzi artifacts authored by A/B):
- Pigozzi ΦID estimand: Gaussian lag-1 MIB-reduced; emergence ≈ synergy + downward causation on ODE GRNs — **observational**, not do-calculus closure.
- Claim ceiling: 808/19 and 17/19 supported; headline **128.32±81.31%** not recovered; ΦID sensitive to lag/binning/partition.
- Proposed interventional design (Agent A audit §6): freeze macro map; held-out clamps; compare macro vs energy-matched micro control; falsify if ΦID rises but macro control fails.
- Guardrail: do **not** equate ΦID / Syn with consciousness, agency, or thermodynamic dissipation.

### Cursor Agent C (Batch 2 code lane — PR naming)

| Artifact | Note |
|---|---|
| Branch `batch2/cursor-c-mne-csd-adapter` → PR **#378** | Fail-closed MNE CSD adapter; footer bcId inaccessible |
| Branch `batch2/cursor-c-3d-chain-audit` | Present on remote |
| PR **#419** body | Attributes companion production PR **#414** to “Cursor Agent C” |
| Agent A digest | Attributes production **#414** / adapter **#378** to **Agent A**, and parity **#419** to **Antigravity C** |

⇒ Letter “C” for spherical-CSD **code** is overloaded (Cursor C vs Agent A ownership narrative). Treat as coordination labels, not a single digestable Intrinsic Existence chat.

### Antigravity Agent C

- Owns **spherical-CSD parity tests PR #419** (`batch2/antigravity-c-spherical-csd-parity`, closed).
- Also related remote branches: `batch2/antigravity-c-binomial-planning`, `batch2/antigravity-c-cochain-hodge-reference`.
- Agent B digest additionally mentions Antigravity/Claude Agent C for cochain reference (#385) and read-only combined verification.
- **No Antigravity cloud bcId** in this Cursor environment list (Antigravity is a separate product/chat surface).

### Codex / Cursor Agent D (serial merger — Batch 2)

- **Sole serial merger** for parallel Batch 2 PRs (A/B digests; Agent A: “Codex Agent D”; Agent B: “Codex/Cursor Agent D”).
- Repo docs: `docs/release/research_cycle_*_2026-09-11.md` authored as “Codex D — Merger Agent.”
- Artifacts from Agent A → D: `codex-d-merge-handoff.md` (#414 MERGE_READY; #378 blocked on mapping), `371-codex-d-handoff.md` (pipeline benchmarks HOLD).
- Agent B usually produced merge-ready packets without merging (exception noted for #453 after gates).

### Cursor Agent D / Antigravity Agent D (Batch 2 code lanes — not the Intrinsic Existence theory chat)

| Lane | Evidence |
|---|---|
| `batch2/cursor-d-streaming-invariance`, `batch2/cursor-d-surrogate-audit` | Remote branches |
| PR **#452** `followup/batch2-cursor-d-dmd-production-…` | Footer bcId inaccessible (best **Cursor D** cloud candidate) |
| PR **#420** `batch2/antigravity-d-dmd-regression` | Antigravity D independent DMD regression / oracles |
| Batch3 `batch3/codex-d-*` | Later Codex D firewall/planner work — still no accessible cloud chat |

---

## 3. Recovered handoff (Agent B → Cursor Agent C)

Written path (historical): `/opt/cursor/artifacts/batch2_agent_b_alpha_estimators/docs/HANDOFF_AGENT_C.md`  
Recovered copy: `/opt/cursor/artifacts/theory-digest/HANDOFF_AGENT_C_RECOVERED.md`

Focus: reuse Agent B synthetic estimator functionals for **statistical simulations** (calibration, FPR, PLV–PLI, sign accuracy) under **HOLD / SYNTHETIC_ONLY**. It does **not** itself implement Pigozzi interventional macro-causal benchmarks; those remain a separate C assignment named in digests.

---

## 4. Why digests for C/D transcripts were not written

Per task instructions, `AGENT_C_DIGEST.md` / `AGENT_D_DIGEST.md` require fetched transcripts (`includeTranscripts:true`).

**Blocked because:**
1. Environment agent list has **no** chats named Agent C / Agent D / Cursor C / Codex D / Antigravity C.
2. Best footer candidates (`bc-5f3561…`, `bc-a4658b9c…`) return **not available** to this principal/environment.
3. Antigravity C/D work lives outside Cursor cloud agent listing.
4. Codex D merger role is evidenced by docs/artifacts/PRs, not by a listable Cursor desktop chat here.
5. Intrinsic Existence “Cursor C owns interventional Pigozzi” appears as a **handoff assignment from A/B**, with no matching accessible run that completed that science lane in this environment.

---

## 5. Science residue for Intrinsic Existence (without C/D transcripts)

If the parent theory digest needs C/D-adjacent science **content**, use these A/B-authored surfaces (not C/D chats):

| Topic | Where |
|---|---|
| Macro causal closure boundary vs Pigozzi ΦID | `AGENT_A_DIGEST.md` §12; `pigozzi-phiid-audit/docs/PIGOZZI_PHIID_REPRODUCTION_AUDIT.md` §6 proposal |
| ΦID Syn fragility / null inflation | `AGENT_B_DIGEST.md` L12 / mission 5721 |
| Sensitivity–capture (κ) | Agent A `sens-capture-reconstruction` artifacts; B deferred interventional ownership to C |
| Spherical CSD (sensor Laplacian, not consciousness) | PRs #414 / #378 / #419 — engineering parity only |
| Estimator panel for further sims | Recovered `HANDOFF_AGENT_C_RECOVERED.md` |

**Claim ban (shared):** no ΦID⇒consciousness, no CSD⇒source localization/biology, no serial-merge logistics as theory evidence.

---

## 6. How to unblock later

1. Re-run `batch-fetch-details` under a principal that owns `bc-5f3561a4-…` and `bc-a4658b9c-…` (or obtain those chats’ environment).
2. Locate Antigravity product chats for Agent C (#419) / Agent D (#420) outside Cursor cloud MCP.
3. Locate Codex merger sessions (CLI/web) if they were never Cursor desktop agents named “Agent D.”
4. If a dedicated Intrinsic Existence Cursor C chat was never started, the interventional Pigozzi lane may exist **only as assignment text** in A/B + the recovered handoff — start a new Agent C run from those packets.

---

## Paths written

| Path | Role |
|---|---|
| `/opt/cursor/artifacts/theory-digest/AGENT_C_D_STATUS.md` | This status (C/D transcripts **not** obtained) |
| `/opt/cursor/artifacts/theory-digest/HANDOFF_AGENT_C_RECOVERED.md` | Full Agent B → Cursor C handoff recovered from B transcript |
| `AGENT_C_DIGEST.md` / `AGENT_D_DIGEST.md` | **Not written** (no transcripts) |
