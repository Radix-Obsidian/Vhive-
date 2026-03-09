"""
Telegram Bot API — official Telegram messaging integration.
Requires a bot token from @BotFather and a target chat_id.
Docs: https://core.telegram.org/bots/api
"""

import os

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramSendToolInput(BaseModel):
    """Input for sending a Telegram message."""

    message: str = Field(..., description="Message text to send (Markdown supported)")
    chat_id: str = Field(
        default="",
        description="Telegram chat ID or @username. Falls back to TELEGRAM_DEFAULT_CHAT_ID env var.",
    )


class TelegramSendTool(BaseTool):
    """Send a Telegram message via the official Bot API."""

    name: str = "TelegramSendTool"
    description: str = (
        "Send a Telegram message via Bot API. "
        "Requires TELEGRAM_BOT_TOKEN env var. "
        "chat_id defaults to TELEGRAM_DEFAULT_CHAT_ID if not provided."
    )
    args_schema: type = TelegramSendToolInput

    def _run(self, message: str, chat_id: str = "") -> str:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        target = chat_id.strip() or os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "").strip()

        if not token:
            return "Error: TELEGRAM_BOT_TOKEN must be set in .env"
        if not target:
            return "Error: Provide chat_id or set TELEGRAM_DEFAULT_CHAT_ID in .env"

        url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
        payload = {
            "chat_id": target,
            "text": message,
            "parse_mode": "Markdown",
        }

        try:
            resp = requests.post(url, json=payload, timeout=20)

            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                return f"Error: Telegram rate limit (429) — retry after {retry_after}s"

            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("result", {}).get("message_id", "N/A")
            return f"Telegram message sent to {target} (message_id: {msg_id})"
        except requests.RequestException as e:
            raise RuntimeError(f"Telegram API error: {e}") from e
