"""F4 T4d: the analysis layer reads result files and never writes (contract "Analysis only reads
result files", ADR-001). Its criteria are written by ``presentation`` (``pilot p1-criteria``)."""

import re
from pathlib import Path

import neuroeco

WRITES = re.compile(
    r"\.write_text\(|\.write_bytes\(|\.mkdir\(|\.unlink\(|\.rename\(|\.touch\(|os\.replace|"
    r"os\.remove|shutil\.|open\([^)]*['\"][wax+]|\.open\(\s*['\"][wax+]|to_csv\(|json\.dump\("
)


def test_the_analysis_package_contains_no_write() -> None:
    analysis = Path(neuroeco.__file__).parent / "analysis"
    found = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sorted(analysis.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if WRITES.search(line)
    ]
    assert found == []
