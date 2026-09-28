# Migration Plan: RL environment → CloudSense product

Target layout: `docs/BUILD_DOC.md` section 12. The RL environment is kept and moved to
`eval/cloudsense_env/` as the offline evaluation harness (section 15).

## Current inventory

| File | What it does |
|---|---|
| `env/models.py` | Pydantic models: `ResourceType`, `Environment`, `ActionType`, `CloudResource`, `CloudAction`, `CloudObservation`, `CloudReward`, `StepResult` |
| `env/environment.py` | `CloudSenseEnv` (reset/step/state/close); cost math; **blast-radius BFS** inline in `_compute_blast_radius` (duplicated for terminate and rightsize); loads `aws_pricing.json` |
| `env/reward.py` | `compute_reward` + helpers (`_is_undersized`, `_is_duplicate_action`, `_breaks_dependency` = direct-dependents check) |
| `env/graders/grader.py` | `grade_task` → `_grade_easy/_medium/_hard` |
| `env/tasks/base_task.py` | `BaseTask`: loads account JSON; abstract `get_correct_actions`, `get_critical_resources`, `get_action_savings` |
| `env/tasks/task_{easy,medium,hard}.py` | 7 / 15 / 40 resource tasks; ground truth; **trap definitions = `get_critical_resources()`** |
| `env/tasks/__init__.py` | `TASKS` registry |
| `env/data/aws_pricing.json` | us-east-1 monthly prices (ec2, rds, s3, lb, nat, es, k8s, ebs, eip, …) |
| `env/data/{easy,medium,hard}_account.json` | Frozen account data (list of `CloudResource` dicts; `dependencies` = ids this resource depends on; `is_critical`; `tags.note`) |
| `env/data/generate_accounts.py` | Offline generator for the account JSONs (reads pricing; not used at runtime) |
| `server/app.py`, `server/routes.py` | FastAPI OpenEnv server: `/reset /step /state /health /version /tasks /close`, `/` dashboard |
| `server/dashboard.py` | Inline HTML dashboard string |
| `inference.py` | LLM baseline agent that drives the env over HTTP (`ENV_URL`, HF router) |
| `tests/test_{models,environment,graders,server,data_consistency}.py` | 76 tests, all passing (Python 3.11) |
| `Dockerfile`, `openenv.yaml` | Container + OpenEnv manifest for the env server (`server.app:app`, port 7860) |
| `pyproject.toml`, `requirements.txt`, `uv.lock` | Package `openenv-cloudsense`; deps: openenv-core, fastapi, uvicorn, pydantic, openai, requests |
| `BUG_ANALYSIS.md`, `README.md` | Env docs |

Where the key pieces live:
- **Pydantic models:** `env/models.py`
- **Account JSON data:** `env/data/*_account.json`
- **Pricing:** `env/data/aws_pricing.json` (read by `env/environment.py` and `env/data/generate_accounts.py`)
- **Account generator:** `env/data/generate_accounts.py`
- **Blast radius:** `env/environment.py::CloudSenseEnv._compute_blast_radius` (BFS over "who depends on me"), plus `env/reward.py::_breaks_dependency` (direct only) and a BFS copy in `tests/test_data_consistency.py`
- **Grader:** `env/graders/grader.py`
- **Reward:** `env/reward.py`
- **Trap resources:** no explicit module; `get_critical_resources()` per task + `is_critical` + `tags.note` in the JSON
- **Server:** `server/`; **inference:** `inference.py`; **tests:** `tests/`

## File mapping

| Existing | Target | Treatment |
|---|---|---|
| `env/models.py` | `eval/cloudsense_env/models.py` | move as-is |
| `env/environment.py` | `eval/cloudsense_env/environment.py` | adapt: pricing path → `backend/candidates/aws_pricing.json`; BFS → `backend.graph.blast_radius` |
| `env/reward.py` | `eval/cloudsense_env/reward.py` | move as-is |
| `env/graders/` | `eval/cloudsense_env/graders/` | move as-is (reused by the eval) |
| `env/tasks/` | `eval/cloudsense_env/tasks/` | move as-is (trap ground truth for `SimulatedEngineer`) |
| `env/data/*_account.json`, `generate_accounts.py` | `eval/cloudsense_env/data/` | move; generator reads pricing from backend |
| `env/data/aws_pricing.json` | `backend/candidates/aws_pricing.json` | move (single source of truth) |
| BFS in `_compute_blast_radius` | `backend/graph/blast_radius.py` | extract as pure `blast_radius(graph, start_id)` |
| `server/` | `eval/cloudsense_env/server/` | move as-is (the OpenEnv HTTP server) |
| `inference.py` | `eval/inference.py` | move as-is |
| `tests/*` | `eval/tests/` | move; fix imports and `DATA_DIR` paths |
| `Dockerfile`, `openenv.yaml` | `eval/` | adapt CMD to `eval.cloudsense_env.server.app:app` (root Dockerfile becomes the backend's in step 15) |
| `pyproject.toml` / `requirements.txt` | root | adapt: product deps (step 1 list), package list, ruff config |
| `README.md`, `BUG_ANALYSIS.md` | `eval/README.md`, `eval/BUG_ANALYSIS.md` | move; new product README in step 15 |

## What the product reuses directly
- `aws_pricing.json` → `backend/candidates/pricing.py` (rules R1–R8 savings).
- Blast-radius BFS → `backend/graph/blast_radius.py`, used by both the product graph and the eval env.
- Trap definitions (`get_critical_resources`, `is_critical`, tag notes) and the grader → the eval's `SimulatedEngineer` (section 15).
- The account generator → `eval/sequence.py` for the 10-scan sequence.

## Risks
- **Imports:** every `from env...` / `from server...` breaks (env, tasks, graders, server routes, all tests). Relative data paths (`Path(__file__).parent / "data"`, `tests/test_data_consistency.py::DATA_DIR`) need updating.
- **`eval` package name** shadows nothing in stdlib as a module, but the Python builtin `eval()` is a common name. Imports like `import eval` are legal; keep usage to `from eval.cloudsense_env import ...`.
- **No existing unit test for blast radius as a function.** Only env-level tests (`tests/test_environment.py:120-150`). Step 1 must add direct tests in `backend/tests/` and keep the env ones passing.
- **Graph direction:** the env stores `dependencies` (what I depend on); the new pure function takes `graph[id] = dependents`. Env must invert edges before calling it. Terminate/rightsize NAT subnet logic stays in the env.
- **Resource type mismatch:** env has `load_balancer`, `kubernetes`, `nat_gateway`, `elasticsearch`; product `Resource.type` is ec2|ebs|snapshot|eip|rds|s3. Adapter (step 3) must skip or map them.
- **Trap archetypes gap:** the 6 archetypes in section 15 (DR standby, payroll batch, audit archive, blue/green, license-pinned, on-call debug) are not explicit in the current data; the eval sequence (step 13) has to generate them.
- **Ruff:** 30 existing violations and no config. Step 1 adds a `[tool.ruff]` config; existing eval code either gets fixed or scoped via per-file ignores.
- **Python version:** system Python is 3.13; project targets 3.11 (use `uv venv --python 3.11`).
- **Docker/OpenEnv:** `openenv.yaml`, Dockerfile and `inference.py` refer to `server.app:app` / port 7860; they must move with the env.
- **Forbidden word:** `docs/BUILD_DOC.md` and the existing git history (commit `73beff8`) contain it; see CLAUDE.md.
