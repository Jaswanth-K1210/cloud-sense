GLOBAL RULES
- Python 3.11, type hints everywhere, Pydantic v2 models, FastAPI, SQLAlchemy 2.0, pytest.
- One task per prompt. Do only what the current prompt asks. Do not refactor unrelated code.
- Never delete the RL environment; it lives in eval/ and its tests must keep passing.
- All secrets come from environment variables via backend/config.py. Never hardcode keys.
  Keep .env.example updated.
- Every external call (AWS, Hindsight, Groq, Slack) goes through one thin wrapper module so
  it can be faked in tests. Tests must never hit real AWS/Hindsight/Groq/Slack.
  Use moto for AWS and in-memory fakes for the others.
- Hindsight SDK: before using any method, confirm its real signature by (a) reading
  https://hindsight.vectorize.io/developer/api/<page> and (b) running
  `python -c "import hindsight_client, inspect; print(inspect.signature(...))"`.
  If the docs and the installed SDK disagree, follow the installed SDK and note it in
  docs/HINDSIGHT_NOTES.md.
- AWS actions must be reversible-first (snapshot before stop/delete), gated by an approved
  verdict, logged to audit_log, and support dry_run=True (default True).
- Resources tagged created_by=terraform or with aws:cloudformation:* tags are NEVER mutated;
  generate a Terraform diff text instead.
- LLM outputs are validated with Pydantic; on failure retry twice with the validation error,
  then fall back to decision="ask". Never crash a scan because of one bad LLM response.
- Never write the word "hackathon" in README, docs, UI copy, commit messages or code comments.
- After each step: run `pytest -q`, run `ruff check .`, fix failures, then summarize the
  changed files and how to verify them manually.

LOCAL NOTES
- Venv: `uv venv --python 3.11 .venv` then `uv pip install --python .venv/bin/python -r requirements.txt`.
- Git: commit locally after each step; never push without asking the owner.
