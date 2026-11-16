"""F4 T4 (I1): the criteria read the files that ``neuroeco pilot p1`` really publishes.

Synthetic configuration only (seed groups >= 1000, t_max = 40, D16) with simulated git facts,
as in the command tests; no real P1 episode, specification or result is created.
"""

from neuroeco.analysis import calibration as crit
from p1_support import make_configs, run_chain, simulate_git


def test_published_iterations_are_evaluated(tmp_path, monkeypatch) -> None:
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    simulate_git(monkeypatch, output)
    run_chain(configs, output)
    for number, stage in ((1, "A"), (2, "B"), (3, "C")):
        block = crit.load_block(output / "calibration" / f"iteration_{number:03d}")
        assert (block.stage, block.scenarios) == (stage, crit.STAGE_SCENARIOS[stage])
        results = crit.evaluate_block(block)
        keys = {r.key for r in results}
        assert ("A4", "b2", "A") in keys and ("A1", "", "") in keys
        assert (("A4", "c", "B-A") in keys) == (stage == "B")
        assert (("B5", "", "C-A") in keys) == (stage == "C")
        assert all(isinstance(r.status, crit.Status) for r in results)
        if stage == "A":
            assert isinstance(crit.requirements_met("A", results), bool)
