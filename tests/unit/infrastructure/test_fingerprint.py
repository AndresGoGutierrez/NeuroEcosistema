"""F4 T4d (D-T4d-2): fingerprints of the code and the environment of P1."""

import json
import platform
from pathlib import Path

from neuroeco.infrastructure import fingerprint
from neuroeco.presentation import pilot_p1


def package(root: Path, files: dict[str, bytes]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def test_the_source_digest_ignores_line_endings_and_order(tmp_path) -> None:
    lf = package(tmp_path / "lf", {"a.py": b"x = 1\ny = 2\n", "b/c.py": b"z = 3\n"})
    crlf = package(tmp_path / "crlf", {"b/c.py": b"z = 3\r\n", "a.py": b"x = 1\r\ny = 2\r\n"})
    digest = fingerprint.source_digest
    assert digest(lf, list(lf.rglob("*.py"))) == digest(crlf, list(crlf.rglob("*.py")))
    renamed = package(tmp_path / "renamed", {"a2.py": b"x = 1\ny = 2\n", "b/c.py": b"z = 3\n"})
    assert digest(renamed, list(renamed.rglob("*.py"))) != digest(lf, list(lf.rglob("*.py")))


def test_the_analysis_code_has_its_own_digest(tmp_path) -> None:
    files = {"domain/rules.py": b"A = 1\n", "analysis/calibration.py": b"B = 1\n"}
    before = fingerprint.code_fingerprint(package(tmp_path / "p", files))
    analysis = fingerprint.code_fingerprint(
        package(tmp_path / "q", {**files, "analysis/calibration.py": b"B = 2\n"})
    )
    simulation = fingerprint.code_fingerprint(
        package(tmp_path / "r", {**files, "domain/rules.py": b"A = 2\n"})
    )
    assert analysis["simulation"] == before["simulation"] != simulation["simulation"]
    assert simulation["analysis"] == before["analysis"] != analysis["analysis"]


def test_the_environment_identifies_what_changes_results_and_nobody(tmp_path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text("lock", encoding="utf-8")
    environment = fingerprint.environment_fingerprint(fingerprint.P1_DEPENDENCIES, lock)
    assert set(environment) == {
        "python",
        "implementation",
        "platform",
        "os",
        "machine",
        "byteorder",
        "dependencies",
        "uv_lock_sha256",
        "thread_env",
        "numpy_cpu_features",
    }
    text = json.dumps(environment)
    for personal in (platform.node(), str(Path.home()), str(tmp_path)):
        assert not personal or personal not in text  # no host name, user or path
    assert environment["numpy_cpu_features"] is not None  # numpy 2 exposes them


def test_pilot_p1_records_the_same_dependencies() -> None:
    assert pilot_p1.DEPENDENCIES == fingerprint.P1_DEPENDENCIES
