from pathlib import Path
import shutil
import subprocess

import pytest

from homelab_creator.spec.safety import contains_poc
from homelab_creator.tools.compose_cli import compose_argv, run_compose


def test_compose_argv_up_is_detach():
    assert compose_argv("up", "docker-compose.yml") == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "up",
        "--detach",
    ]


def test_compose_argv_rejects_unknown():
    with pytest.raises(ValueError):
        compose_argv("build", "docker-compose.yml")


def test_run_compose_confined_to_session(tmp_path: Path):
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  web:\n    image: alpine:3.20.3\n", encoding="utf-8")
    seen: list[tuple[list[str], Path]] = []

    def runner(cmd, cwd):
        seen.append((list(cmd), Path(cwd)))
        return 0, "ok"

    code, out = run_compose(compose, "up", session=tmp_path, runner=runner)
    assert code == 0
    assert seen[0][0][-1] == "--detach"
    assert seen[0][1] == compose.resolve()
    outsider = tmp_path / "other"
    outsider.mkdir()
    (outsider / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="session"):
        run_compose(outsider, "up", session=tmp_path, runner=runner)


def test_run_compose_rejects_host_publish(tmp_path: Path):
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text(
        'services:\n  web:\n    ports:\n      - "8080:80"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="isolation"):
        run_compose(compose, "up", session=tmp_path, runner=lambda cmd, cwd: (0, ""))


def test_run_compose_rejects_missing(tmp_path: Path):
    with pytest.raises(ValueError):
        run_compose(tmp_path, "up", runner=lambda cmd, cwd: (0, ""))


@pytest.mark.docker
def test_docker_compose_config_smoke(tmp_path: Path):
    if not shutil.which("docker"):
        pytest.skip("docker not on PATH")
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text(
        "services:\n  web:\n    image: alpine:3.20.3\n    command: [\"true\"]\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "config"],
        cwd=compose,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "web" in result.stdout
    assert not contains_poc(result.stdout)
