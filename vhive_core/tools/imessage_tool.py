"""
iMessage sending via macOS AppleScript (osascript) — the official Apple-supported method.
No API keys required. Uses the Apple ID signed into Messages.app.
Only works on macOS with Messages.app running and iMessage enabled.
"""

import subprocess

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class iMessageSendToolInput(BaseModel):
    """Input for sending an iMessage."""

    to_contact: str = Field(
        ...,
        description="Recipient phone number (e.g., +12025551234) or Apple ID email address",
    )
    message: str = Field(..., description="Message text to send")


class iMessageSendTool(BaseTool):
    """Send an iMessage via macOS Messages.app using AppleScript. No API keys needed."""

    name: str = "iMessageSendTool"
    description: str = (
        "Send an iMessage to a phone number or Apple ID email. "
        "Requires macOS with Messages.app signed in to iMessage."
    )
    args_schema: type = iMessageSendToolInput

    def _run(self, to_contact: str, message: str) -> str:
        # Escape double quotes in contact and message to prevent AppleScript injection
        safe_contact = to_contact.replace('"', '\\"')
        safe_message = message.replace('"', '\\"').replace("\n", "\\n")

        script = f'''
tell application "Messages"
    set targetService to first service whose service type is iMessage
    set targetBuddy to buddy "{safe_contact}" of targetService
    send "{safe_message}" to targetBuddy
end tell
'''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"iMessage AppleScript error: {err}")
            return f"iMessage sent to {to_contact}"
        except subprocess.TimeoutExpired:
            raise RuntimeError("iMessage timed out — is Messages.app running?")
        except FileNotFoundError:
            raise RuntimeError("osascript not found — iMessage requires macOS")
