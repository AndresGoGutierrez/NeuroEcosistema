"""Helper of the O1 reference test: the step-by-step fingerprint of a seeded episode."""

import hashlib
from pathlib import Path

import numpy as np

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.bootstrap import build_policy, build_runtime
from support import state_digest

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
T_MAX = 300
# (scenario, policy, item, extra overrides); the last case is the P0 stress reference (50/8)
CASES = [
    (scenario, policy, item, ())
    for scenario in "ABC"
    for policy in ("rules", "random")
    for item in (0, 1)
] + [("A", "rules", 0, ("world.n_prey=50", "world.n_predators=8"))]


def episode_fingerprint(scenario: str, policy: str, item: int, extra: tuple[str, ...]) -> str:
    """SHA-256 chained over every step: the state after the step and both observation arrays."""
    runtime = build_runtime(scenario, (f"world.t_max={T_MAX}", *extra), CONFIGS)
    config = runtime.config
    chain = hashlib.sha256()

    def record(trace) -> None:
        chain.update(state_digest(trace.world).encode())
        for array in (trace.prey_observations, trace.predator_observations):
            chain.update(np.ascontiguousarray(array).tobytes())

    run_episode(
        config.world,
        build_policy(policy, "prey", config),
        build_policy(policy, "predator", config),
        runtime.registry,
        EpisodeIdentity(Purpose.PILOT, seed_group=0, item=item),
        on_step=record,
    )
    return chain.hexdigest()


# Recorded on 2026-11-17 on the author's machine (Windows 11, uv.lock of env-frozen-v1) with the
# code BEFORE O1 (commit 2265d87). Bit-for-bit reproducibility holds on the same machine only
# (ADR-016), so these are checked on Windows; the in-process comparison runs everywhere.
RECORDED = {
    ("A", "rules", 0, ()): "1896702cca49f2a8000dea57fa2b224deb6987203a0a3dc83d9f3b2aba9118a0",
    ("A", "rules", 1, ()): "801e4eacc119d3d806ea41315154c372201f32d42b2743722bc3f1ba3ee80148",
    ("A", "random", 0, ()): "44a007bd2180bd2d78414b096761c1a861df2478babd48af8d139769c9abea9e",
    ("A", "random", 1, ()): "fb82e2c64c7f71e81104144adaa34cc11b31239410fb31c655013f303efa2278",
    ("B", "rules", 0, ()): "f5bde66bec8666e7dd6a97099999ea80353d82f9a09da1140c8cf7f53a7e2212",
    ("B", "rules", 1, ()): "19b2518030ade635f7aafe6f8b664ffb50b80c33b2bcb2d4d7ee649b1930f6c7",
    ("B", "random", 0, ()): "1c94b828884741ed56d87f953dfaea84de8a64a3bcf389308a17a23a36995942",
    ("B", "random", 1, ()): "52c448a694b2782ed3104377591dc014420018cd5dd80f51d7dd05fb55075c4a",
    ("C", "rules", 0, ()): "d33056aeed7dcf92126174aaabcad94e80de833cd78f01f1b4fc94874436c357",
    ("C", "rules", 1, ()): "17dc12c21644d633261795645da7dec66aa342dfb5847d862038dedefa0f854c",
    ("C", "random", 0, ()): "330614f781044eebc79265bd6d73261f11e34aa6a5a6e819ea96870a6ee4a8e9",
    ("C", "random", 1, ()): "d703523d191f018c079ac06ca084ce97cb448fdc2c80b930e5902764c440cad0",
    ("A", "rules", 0, ("world.n_prey=50", "world.n_predators=8")): (
        "b000b6be8788ce40d8d67fdf743a861a84ea72394c1badfbf566bd3b6a05d20f"
    ),
}


def encode_nearest_before_o1(observers, target_positions, target_mask, k, vision_radius, size):
    """Verbatim copy of ``perception.encode_nearest`` before O1 (commit 2265d87)."""
    from neuroeco.domain.geometry import (
        minimal_displacement,
        pairwise_distances,
        relative_bearing,
    )
    from neuroeco.domain.perception import VALUES_PER_OBJECT

    n = observers.size
    encoded = np.zeros((n, VALUES_PER_OBJECT * k), dtype=np.float64)
    if n == 0 or target_positions.shape[0] == 0:
        return encoded

    distances = pairwise_distances(observers.positions, target_positions, size)
    perceivable = target_mask[np.newaxis, :] & (distances <= vision_radius)
    masked = np.where(perceivable, distances, np.inf)
    order = np.argsort(masked, axis=1, kind="stable")[:, :k]
    nearest = np.take_along_axis(masked, order, axis=1)
    found = np.isfinite(nearest) & observers.alive[:, np.newaxis]

    displacement = minimal_displacement(observers.positions, target_positions, size)
    selected = np.take_along_axis(displacement, order[:, :, np.newaxis], axis=1)
    forward_unit, left_unit = relative_bearing(selected, observers.headings)

    proximity = np.where(found, 1.0 - np.where(found, nearest, 0.0) / vision_radius, 0.0)
    columns = order.shape[1]
    encoded[:, 0 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity
    encoded[:, 1 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity * left_unit
    encoded[:, 2 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity * forward_unit
    return encoded
