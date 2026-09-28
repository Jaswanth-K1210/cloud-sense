import json

from eval import plot, run_eval


async def test_fake_eval_writes_results_with_expected_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path)
    summary = await run_eval.main(fake=True, seeds=[1], n_scans=3)
    for cond in ("no_memory", "hindsight"):
        run = json.loads((tmp_path / f"{cond}-seed1.json").read_text())
        assert len(run["scans"]) == 3
        assert {"acceptance_rate", "trap_hits", "savings_approved", "suppressed"} <= set(run["scans"][0])
        assert len(summary[cond]["acceptance_mean"]) == 3
    assert summary["meta"]["fake"] is True
    # memory must not make things worse, and should cut trap hits after the first scan
    assert summary["hindsight"]["trap_hits_mean"][-1] < summary["no_memory"]["trap_hits_mean"][-1]
    out = plot.plot(tmp_path / "summary.json", tmp_path / "plot.png")
    assert out.stat().st_size > 10_000


def test_sequence_is_seeded_and_traps_are_mostly_untagged() -> None:
    from eval.sequence import generate

    a, b = generate(7, 2), generate(7, 2)
    assert [r.name for r in a[1].resources] == [r.name for r in b[1].resources]
    traps = [r for s in generate(7, 10) for r in s.resources if r.id.startswith("trap-")]
    assert sum(not r.tags for r in traps) / len(traps) > 0.6
