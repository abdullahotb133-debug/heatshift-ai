# Focused improvement plan

1. Preserve all canonical domain invariants and baseline tests.
2. Align HTTP IDs with domain IDs; bound total request bytes before JSON parsing.
3. Add deterministic ISO 8601 projections of the existing elapsed-seconds clock.
4. Record explicit before/after versions and preserve same-timestamp commit event order.
5. Allow explicit configurable task count while preserving the six-task default and
   rejecting mismatched definition counts. Never change worker qualifications at runtime.
6. Extend the existing HTTP mock demo with an operationally invalid assignment rejection.
7. Test the changes, full regression, all scenarios, OpenAPI equality, real HTTP startup
   and deterministic replay. Regenerate examples/contracts and publish the existing repo.

No new runtime dependencies, service, risk model, scheduler, frontend or database.
Future sensor transport remains behind EnvironmentAdapter; physical integration is
UNVERIFIED, not simulated success. Docker and production deployment remain UNVERIFIED.
