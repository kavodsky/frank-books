"""The layering is only real if a test checks it (roadmap 0.1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")


@pytest.mark.architecture
def test_import_contracts_hold():
    """`frank.domain` imports nothing external and dependencies point inwards."""
    result = subprocess.run(
        [str(LINT_IMPORTS)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
