# Component B authoritative package and milestone register

Corrective reconciliation: 2026-10-24. Source: Project Owner's original
**Component B Master Developer Brief**, sections 4–7. This file records that plan;
it does not authorize another package.

## Packages and dependencies

| Register order | Package / platform | Scope and prerequisites |
| --- | --- | --- |
| 1–4 | G1–G4 / GitHub + Codex | Contract review; risk engine; decision engine; tests and integration validation. G2 depends on valid A mappings; G3 on G2; G4 verifies the supported chain. |
| 5 | C1 / Codespaces | Reproducible development environment. Next listed package, NOT STARTED or authorized by this corrective task. |
| 6 | C2 / Codespaces | Actual runtime/API/test verification, after environment setup. |
| 7 | C3 / Codespaces | Integrated B test environment and evidence; requires relevant G2/G3/G4 functionality. |
| 8–9 | R1–R2 / Render | Hosted integrated service, then external runtime/state verification; no deployment in this task. |
| 10–12 | N1–N3 / n8n | Snapshot acquisition; orchestration; verification/failure/audit coordination. Requires verified inputs, decisions, command semantics and runtime. |
| 13–15 | S1–S3 / Supabase | Schema; persistence; audit integrity/access. Persistence requirements also inform orchestration; register order does not remove dependencies. |

G-series is the repository/backend stream. C-series is the reproducible environment
and verification stream, not a second runtime microservice. The fifth entry is C1;
it is **not an official package called G5**.

**G5: UNDEFINED — REQUIRES PROJECT OWNER CONFIRMATION.** A later G4 instruction
mentioned G5 without a scope. No new scope, milestone or renumbering is inferred.
The original context-only brief is now used as the sequencing authority requested
by the corrective instruction, not as permission to execute C1.

## Original milestones — identifiers preserved

| Milestone | Original name | Contributing packages |
| --- | --- | --- |
| M1 | Foundation | G1, C1, C2 |
| M2 | Risk | G2, G4 |
| M3 | Decision | G3, G4 |
| M4 | Persistence | S1, S2, S3 |
| M5 | Runtime | R1, R2 |
| M6 | Automation | N1, N2, N3 |
| M7 | Verification | G4, C3, R2, N3, S3 |

The later G4 prompt's “M4 — Backend Validation & Integration Readiness” heading
conflicts with this register. G4 contributes verification to M2/M3/M7 and does not
rename the original M4 Persistence milestone.

## Current state

- A: existing verified local baseline; no production A change in this correction.
- G1: original PARTIAL remote-access assessment; G2 later matched A baseline files
  to remote commit 31c2b3b146324888a6581558f739a23ab26025bd.
- G2: verified retrospective one-hour scope; corrective prospective extension uses
  the same calculation and explicit simulation forecasts.
- G3: original PARTIAL report remains historical evidence. Corrective version
  0.2.0 adds conditional candidate selection, preserving unresolved affected-worker
  exposure and mandatory human review.
- G4: original 492-test run and PARTIAL readiness verdict remain valid records of
  its original scope. A later correction does not retroactively make G4 failed.
- Corrective task: see COMPONENT_B_CORRECTIVE_VERIFICATION.md for executed results,
  unresolved limits and current readiness.
- C1/C2/C3, hosting, orchestration, persistence and dashboard are not completed by
  this corrective task. No whole milestone is upgraded merely because tests pass.
- GitHub write access was reverified on 2026-10-24 by publishing an empty commit
  on `codex/access-check-20261024`; the former 403 blocker is resolved. The final
  review reconciles the 14 local B deliverables with the unchanged A baseline;
  see [current review and delivery manifest](PRE_G5_REPOSITORY_REVIEW.md).

Next listed package: **C1**, subject to explicit Project Owner authorization.
Before any automated safety-command workflow, resolve affected-worker protection,
forecast-horizon enforcement, review enforcement and operational input provisioning.
G5 remains undefined unless the owner supplies a separate confirmed specification.

