"""F4 T4-I4: selection of the winner of each grid of a round (ADR-033 P1-17, D4).

Synthetic rows with only the columns the selection reads; no episode is run (T4c will run the
rounds).
"""

import pytest

from neuroeco.analysis import calibration as crit

FLEE = (0.2, 0.3, 0.4, 0.5)
CRUISE = (0.3, 0.5, 0.7)
VALUES = {
    "plant_energy": 30.0,
    "regrow_delay": 50,
    "n_plants_a": 40,
    "n_plants_b": 15,
    "n_predators_c": 8,
    "prey_flee_threshold": 0.3,
    "prey_cruise_fraction": 0.5,
    "predator_cruise_fraction": 0.5,
}


def prey_rows(totals: dict[tuple[float, float], int], episodes: int = 2) -> list[dict]:
    """Rules rows of A for the 12 combinations; ``totals`` overrides the default sum 100."""
    rows = []
    for p in FLEE:
        for u in CRUISE:
            total = totals.get((p, u), 100)
            for item in range(episodes):
                share = (
                    total - total // episodes * (episodes - 1) if item == 0 else total // episodes
                )
                rows.append(
                    row(
                        item,
                        prey_flee_threshold=p,
                        prey_cruise_fraction=u,
                        prey_survival_numerator=share,
                    )
                )
    return rows


def predator_rows(totals: dict[float, int]) -> list[dict]:
    return [
        row(item, predator_cruise_fraction=u, prey_captured=totals[u] // 2)
        for u in CRUISE
        for item in range(2)
    ]


def row(item: int, **values) -> dict:
    return {
        "scenario": "A",
        "condition": "rules",
        "seed_group": 1000,
        "item": item,
        **VALUES,
        "prey_survival_numerator": 0,
        "prey_captured": 0,
        **values,
    }


@pytest.mark.parametrize(
    ("totals", "current", "winner", "rule"),
    [
        ({(0.4, 0.7): 101}, (0.3, 0.5), (0.4, 0.7), "unique"),  # a strict improvement wins
        ({(0.4, 0.7): 101, (0.3, 0.5): 101}, (0.3, 0.5), (0.3, 0.5), "current"),
        ({(0.4, 0.7): 101, (0.5, 0.5): 101}, (0.3, 0.5), (0.5, 0.5), "lowest u_cruise"),
        ({(0.4, 0.3): 101, (0.2, 0.3): 101}, (0.3, 0.5), (0.2, 0.3), "lowest p_flee"),
        ({}, (0.3, 0.5), (0.3, 0.5), "current"),  # all 12 tied: nothing changes
        ({}, (0.35, 0.5), (0.2, 0.3), "lowest p_flee"),  # current outside the grid
    ],
)
def test_prey_selection_and_ties(totals, current, winner, rule) -> None:
    selection = crit.select_prey(prey_rows(totals), FLEE, CRUISE, current)
    assert (selection.winner, selection.rule) == (winner, rule)
    assert selection.objective == max(selection.totals.values())
    assert len(selection.totals) == 12  # every combination is recorded (P1-4)


@pytest.mark.parametrize(
    ("totals", "current", "winner", "rule"),
    [
        ({0.3: 10, 0.5: 12, 0.7: 14}, 0.5, (0.7,), "unique"),
        ({0.3: 14, 0.5: 12, 0.7: 14}, 0.7, (0.7,), "current"),
        ({0.3: 12, 0.5: 14, 0.7: 14}, 0.3, (0.5,), "lowest u_cruise"),
    ],
)
def test_predator_selection_and_ties(totals, current, winner, rule) -> None:
    selection = crit.select_predator(predator_rows(totals), CRUISE, current)
    assert (selection.winner, selection.rule, selection.objective) == (
        winner,
        rule,
        max(totals.values()),
    )


def drop(rows, p, u):
    return [r for r in rows if (r["prey_flee_threshold"], r["prey_cruise_fraction"]) != (p, u)]


@pytest.mark.parametrize(
    ("rows", "flee", "message"),
    [
        (drop(prey_rows({}), 0.5, 0.7), FLEE, "without episodes"),
        (
            [*prey_rows({}), row(0, prey_flee_threshold=0.2, prey_cruise_fraction=0.3)],
            FLEE,
            "duplicated episode",
        ),
        ([*prey_rows({}), row(0, prey_flee_threshold=0.25)], FLEE, "not in the grid"),
        (drop(prey_rows({}), 0.2, 0.3) + prey_rows({}, episodes=1)[:1], FLEE, "same episodes"),
        ([*prey_rows({})[:-1], {**prey_rows({})[-1], "seed_group": 1001}], FLEE, "one seed group"),
        (
            [*prey_rows({})[:-1], {**prey_rows({})[-1], "regrow_delay": 60}],
            FLEE,
            "outside the grid",
        ),
        ([*prey_rows({})[:-1], {**prey_rows({})[-1], "scenario": "B"}], FLEE, "scenario A"),
        ([], FLEE, "no episodes"),
        (prey_rows({}), (0.2, 0.2, 0.3, 0.4, 0.5), "twice"),
    ],
)
def test_incomplete_or_incoherent_grids_stop_the_selection(rows, flee, message) -> None:
    with pytest.raises(crit.CriteriaError, match=message):
        crit.select_prey(rows, flee, CRUISE, (0.3, 0.5))
