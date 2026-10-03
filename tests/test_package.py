"""Task 0: package is importable and the module CLI exposes help."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import homelab_creator
from homelab_creator.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


def test_package_importable() -> None:
    assert homelab_creator.__version__


def test_main_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_module_help_subprocess() -> None:
    exe = next(
        (p for p in ("/usr/bin/python3.13", "/usr/bin/python3") if Path(p).exists()),
        None,
    )
    if exe is None:
        pytest.skip("no system python3 at /usr/bin/python3")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [exe, "-m", "homelab_creator", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "homelab" in result.stdout.lower()
