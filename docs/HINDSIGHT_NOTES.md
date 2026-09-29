# Hindsight SDK notes (verified)

Installed: `hindsight-client==0.10.1`. Signatures checked with `inspect.signature` and against
https://hindsight.vectorize.io/developer/api/{retain,operations,memories} on 2026-09-28.
Where BUILD_DOC and the SDK disagree, the SDK wins; each case is listed below.

| Need | Real call (0.10.1) | Differs from BUILD_DOC? |
|---|---|---|
| Client + Cloud auth | `Hindsight(base_url, api_key=None, timeout=300.0)`; api_key is sent as `Authorization: Bearer <key>` | Resolves the ⚠ VERIFY in 5.2 |
| Create bank (idempotent) | `acreate_bank(bank_id, name=, mission=, disposition_skepticism=, disposition_literalism=, disposition_empathy=)` (PUT = create or update) | Disposition is three int kwargs (1–5), not a dict. No `directives=` kwarg |
| Directives | `acreate_directive(bank_id, name, content, priority=0, is_active=True)`, `alist_directives(bank_id)` → `.items[].name/.content` | Separate API, one call per directive |
| Mental-model refresh interval | Per model: `trigger["min_refresh_interval_seconds"]`; per bank: `aupdate_bank_config(mental_model_min_refresh_interval_seconds=)` | Set on the trigger |
| Retain | `aretain_batch(bank_id, items=[{content, timestamp, context, metadata, entities, tags, observation_scopes}], document_id=)` | **`retain()` has no `observation_scopes` kwarg**; only batch items carry it. `metadata` values must be `str` |
| observation_scopes | `list[list[str]]` or `"per_tag"`/`"combined"`/`"shared"`. `[]` as an **inner** list = the global untagged scope (`"shared"` ≡ `[[]]`). An empty **outer** list falls back to `combined` | Spec format `[[], [account:x], [team:y]]` is valid |
| Recall | `arecall(bank_id, query, max_tokens=4096, tags=None, tags_match="any", types=None, budget="mid")` → `.results[]: id, text, type, tags, document_id, metadata, source_fact_ids` | No per-result score in `RecallResult` other than optional `scores` |
| Reflect | `areflect(bank_id, query, include_facts=True)` → `.text`, `.based_on.memories[]`, `.based_on.mental_models[]` | **`based_on` is empty unless `include_facts=True`** (default False). It is an object with `memories`, `mental_models`, `directives`; answers often cite the playbook mental model rather than raw facts |
| Mental model create | `acreate_mental_model(bank_id, name, source_query, tags=None, max_tokens=None, trigger=dict, id="org-playbook")` | `id` kwarg (not `mental_model_id`) |
| Mental model get | `aget_mental_model(bank_id, mental_model_id, detail="full")` → `.content`, `.last_refreshed_at`, `.reflect_response` (dict; structured output at `reflect_response["structured_output"]`) | Spec's `pb.reflect_response.structured_output` is a dict key, not an attribute |
| Mental model history | `aget_mental_model_history(bank_id, mental_model_id)` → list of `{previous_content, changed_at}` (most recent first) | — |
| List observations (rules) | `alist_memories(bank_id, type="observation", limit=100)` → `.items[]: id, text, proof_count, tags, source_memory_ids, state, updated_at` | — |
| Fetch one memory | `hs.memory.get_memory(bank_id, memory_id)` (low-level, async) | — |
| **Delete a rule** | No delete-memory endpoint. Observations are derived and cannot be curated directly. We **invalidate the observation's source facts**: `hs.memory.update_memory(bank_id, id, UpdateMemoryRequest(state="invalidated", reason=...))`. Hindsight then drops/re-derives the observation | Spec says "delete a memory through the Memories API"; the real mechanism is invalidate (auditable, restorable) |
| Operations / consolidation wait | `hs.operations.list_operations(bank_id, status="pending"|"processing")` → `.total`, `.operations[]` (low-level, async) | Resolves 5.7 |
| Bank templates | `hs.banks`/`bank_templates_api`: `export_bank_template`, `import_bank_template`, `get_bank_template_schema` | CloudSense seeds its own 10 rules via retain (5.9) instead of a template import |

Consolidation is asynchronous and bank-deduplicated; `wait_for_consolidation` polls
pending + processing operations until both are zero or the timeout passes.
Measure the real latency with `python -m backend.memory.smoke`.
Client instances are cached per running event loop via weak references (`_per_loop`) to avoid loop-mismatch errors across async tasks.
