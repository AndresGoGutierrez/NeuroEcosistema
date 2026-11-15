"""Test support values.

``PROVISIONAL_*`` mirror the provisional pre-P1 values approved for F1 (decision A5 in
docs/phase_gates.md). They exist only to exercise the code; P1 replaces them.
"""

from neuroeco.domain.params import SpeciesParams, WorldParams

PROVISIONAL_PREY = SpeciesParams(
    v_max=1.0,
    omega_max=0.5,
    vision_radius=20.0,
    e_max=100.0,
    initial_energy_fraction=0.8,
    c_basal=0.16,
    c_move=0.32,
)

PROVISIONAL_PREDATOR = SpeciesParams(
    v_max=1.3,
    omega_max=0.3,
    vision_radius=20.0,
    e_max=100.0,
    initial_energy_fraction=0.8,
    c_basal=0.16,
    c_move=0.32,
)

PROVISIONAL_WORLD = WorldParams(
    size=150.0,
    t_max=1000,
    n_prey=25,
    n_predators=3,
    n_plants=40,
    regrow_delay=50,
    capture_radius=2.5,
    eat_radius=1.5,
    plant_energy=30.0,
    prey_energy=40.0,
    prey=PROVISIONAL_PREY,
    predator=PROVISIONAL_PREDATOR,
)
