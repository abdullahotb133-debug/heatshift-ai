# Stage 9 — HTTP API and contracts

PASS: 14 endpoints, version 1.0 schemas/OpenAPI, validated command batches, bearer auth,
explicit CORS, deployment configuration, optimistic version checks, process identity,
idempotency and single-writer candidate transactions. All endpoint examples executed.
Existing engine/domain APIs preserved; framework dependencies confined to HTTP boundary.
24 API/demo tests included in final 357 passing tests. No blocked acceptance items.
See COMPONENT_A_API_CONTRACT.md and COMPONENT_A_TEST_REPORT.md for evidence and limits.

2026-10-23 review: added deterministic ISO timestamps, explicit commit versions,
same-time event order, request byte limit and aligned ID validation. Exported OpenAPI
and all 14 examples regenerated. Final regression: 369 passing tests.
