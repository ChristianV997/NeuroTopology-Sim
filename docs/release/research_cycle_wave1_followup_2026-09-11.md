# Research-cycle wave 1 follow-up audit

**Agent:** Codex D — Merger Agent  
**Base:** `origin/main` at `9b7c1079cde25bc3c0b124df3bf8057e97a035a9`  
**Follow-up branch:** `codex/research-cycle-wave1-followup-20260911`

Five PRs appeared after the first wave had already merged through PR #315.
Their heads were independently fetched and tested against the newer live main.

| PR | Head | Focused result | Decision |
|---:|---|---:|---|
| 310 | `3e13b778c4c8` | 21 passed | Integrated; local cross-platform acceptance harness |
| 311 | `dcf885295014` | 16 passed | Integrated; operational release-evidence evaluator |
| 312 | `2d88f4df8066` | 28 passed, 3 Windows/POSIX wrapper skips after fix | Integrated with existing-output path guard and platform-correct skips |
| 313 | `3a7c251d81ba` | 36 passed | Integrated with strict non-finite JSON token rejection |
| 314 | `da5f639bbd5a` | 18 passed before integration | Integrated after removing implicit missing-verdict PASS promotion |

The three #312 failures on the original branch were Windows invocation
failures caused by passing native Windows paths to a POSIX bash executable.
They are now explicit platform skips on Windows; the PowerShell path remains
the supported Windows wrapper. The safety scanner also rejects existing
absolute paths supplied to explicit output flags unless they are inside the
declared output directory.

#314’s loader now gives an absent or unknown validation verdict
`REVIEW_REQUIRED`/`unknown` evidence status and emits no support/contradiction
edge. #313 rejects JSON non-finite constants at read time instead of allowing
them to fail later during report hashing.

These changes remain operational/audit surfaces. They do not emit scientific
PASS, causal claims, formal Bayes factors, or empirical promotion from
synthetic/proxy/partial records.

