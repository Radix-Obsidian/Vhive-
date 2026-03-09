"""
Custom tool connecting CrewAI to dynamic Docker sandbox via fleet_manager.
Uses ContainerManager (Docker Python SDK) for isolated execution.
Streams stdout/stderr to Star-Office-UI WebSocket when broadcaster is active.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from vhive_core.fleet_manager import execute_in_container


class OpenHandsExecuteToolInput(BaseModel):
    """Input for executing code in sandbox."""

    code: str = Field(..., description="Python or JavaScript code to execute")
    language: str = Field(default="python", description="Language: python or javascript")


class OpenHandsExecuteTool(BaseTool):
    """
    Execute code in an isolated Docker container via fleet_manager.
    Uses ubuntu:latest for Python, node:alpine for JavaScript.
    Returns stdout/stderr to the agent; streams to /ws when Star-Office-UI is running.
    """

    name: str = "OpenHandsExecuteTool"
    description: str = "Execute Python or JavaScript code in an isolated Docker container. Use for testing/compiling digital products."
    args_schema: type = OpenHandsExecuteToolInput

    def _run(self, code: str, language: str = "python") -> str:
        try:
            result = execute_in_container(code, language=language)

            # Stream to WebSocket clients (no-op if broadcaster has no queue consumer)
            try:
                from vhive_core.stream_bus import broadcaster

                broadcaster.emit_sync(
                    "docker_terminal",
                    {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.exit_code,
                        "container_id": result.container_id,
                    },
                )
            except ImportError:
                pass

            out = result.stdout or ""
            err = result.stderr or ""
            if result.exit_code != 0:
                return f"stderr:\n{err}\nstdout:\n{out}\nexit_code={result.exit_code}"
            return f"stdout:\n{out}" + (f"\nstderr:\n{err}" if err else "")
        except Exception as e:
            return f"Error executing in container: {e}"
