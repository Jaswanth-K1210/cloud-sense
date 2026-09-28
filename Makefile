PY ?= .venv/bin/python
REGION ?= us-east-1

.PHONY: install test lint run demo seed teardown lookalike eval eval-fake plot smoke-memory frontend

install:            ## Python 3.11 venv + dev deps + frontend deps
	uv venv --python 3.11 .venv
	uv pip install --python $(PY) -r requirements-dev.txt
	cd frontend && npm ci

test:               ## backend + eval tests, then the frontend build
	$(PY) -m pytest -q
	cd frontend && npm run build

lint:
	$(PY) -m ruff check .
	.venv/bin/cfn-lint infra/*.yaml

run:                ## API on :8000 (uses .env)
	$(PY) -m backend.store.seed_demo
	$(PY) -m uvicorn backend.app:app --reload --port 8000

demo:               ## API with no external services (fake memory + LLM, eval accounts instead of AWS)
	APP_ENV=offline DATABASE_URL=sqlite:///offline-demo.db $(PY) -m backend.store.seed_demo
	APP_ENV=offline DATABASE_URL=sqlite:///offline-demo.db $(PY) -m uvicorn backend.app:app --port 8000

frontend:           ## dashboard dev server on :5173
	cd frontend && npm run dev

seed:               ## create the demo estate in the sandbox account (costs money; see infra/billing-alarm.md)
	$(PY) infra/sandbox-seed/seed.py --region $(REGION)

teardown:
	$(PY) infra/sandbox-seed/seed.py --region $(REGION) --teardown

lookalike:
	$(PY) infra/sandbox-seed/launch_lookalike.py --region $(REGION)

eval:               ## real Hindsight + Groq, 3 seeds
	$(PY) -m eval.run_eval && $(PY) -m eval.plot

eval-fake:          ## offline harness check, seconds
	$(PY) -m eval.run_eval --fake && $(PY) -m eval.plot

smoke-memory:       ## real Hindsight: retain -> consolidate -> recall, prints latency
	$(PY) -m backend.memory.smoke
