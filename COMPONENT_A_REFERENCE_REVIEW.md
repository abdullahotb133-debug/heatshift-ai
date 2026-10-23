# External engineering reference review — 2026-10-23

Actual implementation files were read through the GitHub connector. No third-party
source code or worker/task models were copied. Observations below are code inspection,
not claims that the other projects were executed or independently verified here.

| Repository / files inspected | Observed approach | Applicable idea / excluded scope |
|---|---|---|
| [SilentKnight742](https://github.com/SilentKnight742/heatshift-ai): backend/app/clients/fortyguard.py; docs/api-testing.md, testing.md, third-party-evaluator-guide.md | Explicit live/cached provenance and captured time; missing sentinel normalization; bounded provider retry; documented API journeys | Preserve source/freshness, executable evidence and explicit fallback. Do not adopt scoring, optimization or Supabase |
| [Eng-Ahmed-Hossam](https://github.com/Eng-Ahmed-Hossam/heatshift-ai/tree/feat/data-model-and-impact-metrics): backend/sim/clock.py, sim/scenario.py, api/routes.py, scheduler/validator.py | Shared clock, chronological due-event execution, thin routes, pre-application constraint validator | Preserve a single clock and command validation. Do not adopt wall-clock pumping, agent loop, thermal risk bands or scheduling |
| [Aseel-Sh](https://github.com/Aseel-Sh/HeatShift): lib/weather/open-meteo.ts; docs/ARCHITECTURE.md, INTEGRATIONS.md, SCHEDULER.md | Inward domain dependencies; validates provider arrays and date coverage; typed errors/timeouts; documents a body limit | Boundary validation and bounded requests; distinguish forecast from field inputs. Do not import Saudi scheduling restrictions or TWL rules |
| [NaxeCode](https://github.com/NaxeCode/heatshift): src/lib/contracts.ts; docs/VERIFICATION.md | Bounded schemas, nullable uncertainty, timestamps/source in forecast contracts; verification report distinguishes actual runs and limitations | Add precise timestamp/version contracts and repeatable evidence. Do not adopt model extraction, Miami scheduling or impact metrics |
| [Pizzylee001](https://github.com/Pizzylee001/heatshift): app/api/fortyguard/route.ts | Validates sites/hours, limits concurrency and retries, reports partial results, only caches complete results; no fabricated missing values | Preserve explicit missing inputs and failure states. Do not add provider polling or external dependencies to deterministic core |

## Licensing and attribution

SilentKnight742 and NaxeCode root LICENSE files explicitly contain MIT licenses, with
2026 contributor copyrights. Copying their substantial code would require retaining
copyright and permission notices; this change copies none. GitHub metadata reports no
license for Eng-Ahmed-Hossam, Aseel-Sh or Pizzylee001; no reuse permission is assumed.
The Aseel/Pizzylee recursive trees exposed no license file. Those projects are references
only. Attribution links above identify architectural inspiration, not reused source.

Observed tree revisions: SilentKnight742 419158ad02af98e180c72e25bab97a69bf31ab2c;
Aseel-Sh 0cdfae68de4d2eac3fe6dc93a9b85b1710aa7eaf;
NaxeCode 118a71a4138fea6004b973f61378385584a06c23;
Pizzylee001 6b74b35c1bfb87f50b4bdaf6b51ae97e59a7fa09.
Eng-Ahmed-Hossam files were read on the explicitly requested branch; recursive-tree
fetch failed, so no whole-tree revision verification is claimed.

No external scientific thresholds were adopted. Source reviews do not establish
scientific correctness, field validation or production reliability of these projects.
