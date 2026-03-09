"""
Tweepy integrations for Twitter API v2.
Search/trends and DM sending. Handles TooManyRequests for graph retry.
"""

import os

import tweepy
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class TwitterSearchToolInput(BaseModel):
    """Input for Twitter search/trends."""

    query: str = Field(..., description="Search query or topic (e.g., digital products, compliance)")


class TwitterSendDMToolInput(BaseModel):
    """Input for sending Twitter DM."""

    recipient_id: str = Field(..., description="Twitter user ID of recipient")
    message: str = Field(..., description="DM message text")


class TwitterSearchTool(BaseTool):
    """Search Twitter for trends and conversations via API v2."""

    name: str = "TwitterSearchTool"
    description: str = "Search Twitter for trends, hashtags, and conversations. Use for market research."
    args_schema: type = TwitterSearchToolInput

    def _run(self, query: str) -> str:
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
        if not bearer_token:
            return "Error: TWITTER_BEARER_TOKEN must be set in .env"

        try:
            client = tweepy.Client(bearer_token=bearer_token)
            # Search recent tweets (last 7 days on free tier)
            response = client.search_recent_tweets(
                query=query,
                max_results=10,
                tweet_fields=["created_at", "public_metrics"],
                expansions=["author_id"],
                user_fields=["username", "name"],
            )

            if not response.data:
                return f"No tweets found for query: {query}"

            tweets = []
            users = {u.id: u for u in (response.includes.get("users") or [])}
            for t in response.data:
                u = users.get(t.author_id)
                uname = u.username if u else "unknown"
                tweets.append(f"@{uname}: {t.text[:100]}...")
            return "\n".join(tweets[:5])
        except tweepy.TooManyRequests:
            raise RuntimeError("Twitter rate limit (429) - graph will retry") from None
        except tweepy.TweepyException as e:
            # Non-rate-limit errors (402 credits depleted, 403, etc.) — return as string
            # so the research agent falls back to LLM knowledge instead of crashing the graph.
            return f"Twitter unavailable ({e}). Use your training knowledge for trend research."


class TwitterSendDMTool(BaseTool):
    """Send Twitter DM via API v2. Requires OAuth 1.0a user context."""

    name: str = "TwitterSendDMTool"
    description: str = "Send a direct message to a Twitter user. Requires recipient user ID."
    args_schema: type = TwitterSendDMToolInput

    def _run(self, recipient_id: str, message: str) -> str:
        api_key = os.getenv("TWITTER_API_KEY", "").strip()
        api_secret = os.getenv("TWITTER_API_SECRET", "").strip()
        access_token = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
        access_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "").strip()

        if not all([api_key, api_secret, access_token, access_secret]):
            return "Error: TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET must be set for DMs"

        try:
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret,
            )
            resp = client.create_direct_message(participant_id=recipient_id, text=message, user_auth=True)
            if resp and resp.data:
                return f"DM sent to {recipient_id}"
            return "DM may have been sent (check API response)"
        except tweepy.TooManyRequests:
            raise RuntimeError("Twitter rate limit (429) - graph will retry") from None
        except tweepy.TweepyException as e:
            return f"Twitter DM unavailable ({e}). Skip Twitter and use iMessage or Telegram instead."
