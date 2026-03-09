"""
Dynamic Sandboxing: Container fleet manager using the official Docker Python SDK.
Allows the LangGraph orchestrator to programmatically run(), execute(), and stop()
isolated Docker containers (ubuntu:latest or node:alpine) for agent tasks.
Returns stdout/stderr to the agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import docker

# Default images for Python vs Node execution (per MID: ubuntu:latest or node:alpine)
PYTHON_IMAGE = "ubuntu:latest"
NODE_IMAGE = "node:alpine"


@dataclass
class ExecutionResult:
    """Result of a command execution inside a container."""

    stdout: str
    stderr: str
    exit_code: int
    container_id: str


class ContainerManager:
    """
    Manages ephemeral Docker containers for isolated agent task execution.
    Use run() to spawn, execute() to run commands, stop() to tear down.
    """

    def __init__(self, image: str = PYTHON_IMAGE, workdir: str = "/workspace"):
        self.image = image
        self.workdir = workdir
        self._client: Optional[docker.DockerClient] = None
        self._container: Optional[docker.models.containers.Container] = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def run(
        self,
        *,
        image: Optional[str] = None,
        volumes: Optional[dict[str, dict]] = None,
        environment: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Spin up an isolated Docker container. Returns container ID.
        Uses ubuntu:latest or node:alpine by default based on image param.
        """
        img = image or self.image
        vol = volumes or {}
        env = environment or {}

        self._container = self.client.containers.run(
            img,
            command="tail -f /dev/null",  # Keep container alive
            detach=True,
            remove=False,
            volumes=vol,
            working_dir=self.workdir,
            environment=env,
        )
        if hasattr(self._container, "id"):
            return self._container.id
        return str(self._container)

    def execute(
        self,
        command: str | list[str],
        *,
        workdir: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a command inside the running container.
        Returns stdout, stderr, and exit code.
        """
        if self._container is None:
            raise RuntimeError("Container not running. Call run() first.")

        wd = workdir or self.workdir
        if isinstance(command, str):
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = command

        result = self._container.exec_run(cmd, workdir=wd, demux=True)

        stdout_b = result.output[0] or b""
        stderr_b = result.output[1] or b""
        exit_code = result.exit_code if result.exit_code is not None else 0

        return ExecutionResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=exit_code,
            container_id=self._container.id,
        )

    def stop(self) -> None:
        """Tear down the container."""
        if self._container is not None:
            try:
                self._container.stop(timeout=5)
                self._container.remove()
            except docker.errors.APIError:
                pass
            finally:
                self._container = None

    def __enter__(self) -> "ContainerManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


def execute_in_container(
    code: str,
    language: str = "python",
    *,
    image: Optional[str] = None,
    mount_path: Optional[str] = None,
) -> ExecutionResult:
    """
    One-shot: create container, write code to file, execute, tear down.
    Returns ExecutionResult with stdout/stderr.
    """
    import tempfile
    import uuid
    from pathlib import Path

    ext = "py" if language.lower() in ("python", "py") else "js"
    runner = "python3" if ext == "py" else "node"
    img = image or (PYTHON_IMAGE if ext == "py" else NODE_IMAGE)

    with tempfile.TemporaryDirectory() as tmpdir:
        fname = f"{uuid.uuid4().hex}.{ext}"
        filepath = Path(tmpdir) / fname
        filepath.write_text(code, encoding="utf-8")

        volumes = {str(tmpdir): {"bind": "/workspace", "mode": "rw"}}
        cmd = [runner, f"/workspace/{fname}"]

        with ContainerManager(image=img, workdir="/workspace") as mgr:
            mgr.run(volumes=volumes)
            result = mgr.execute(cmd)
        return result
