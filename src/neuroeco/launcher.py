"""Console entry point (ADR-016).

Sets single-threaded defaults for the numerical libraries BEFORE anything imports numpy, then
starts the CLI. Variables already defined by the user are respected. This is the complementary
early layer of ADR-016; the authoritative runtime control (threadpoolctl) arrives in F6.
"""

from __future__ import annotations

import os

THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def configure_environment() -> None:
    for name in THREAD_VARIABLES:
        os.environ.setdefault(name, "1")


def main() -> None:
    configure_environment()
    from neuroeco.presentation.cli import app  # imported only after the environment is set

    app()


if __name__ == "__main__":
    main()
