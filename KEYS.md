# Vhive — API Keys & Credentials Reference

Everything you need to run AURA 100%. Get them in order.

---

## 1. Ollama (Local LLM — No Key)

No account needed. Install and pull models.

Install:        https://ollama.com/download
After install:

    ollama pull qwen2.5-coder    # coding tasks
    ollama pull llama3            # creative / outreach tasks
    ollama serve                  # keep running (auto-starts on macOS after install)

Verify:         python -m vhive_core.main --check

---

## 2. Shopify Admin API

Required for: creating products, reading orders, revenue tracking.

Where to get it:
  1. Go to https://admin.shopify.com/store/YOUR-STORE/settings/apps/development
  2. Click "Create an app" → give it a name (e.g., AURA)
  3. Under "Configuration" → "Admin API access scopes", enable:
       - read_products, write_products
       - read_orders
  4. Click "Install app" → copy the Admin API access token (shown once, starts with shpat_)

Env vars to set:
    SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com    # no https://, no trailing slash
    SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxx
    SHOPIFY_API_VERSION=2026-01                     # already set in .env.example

Direct link:    https://admin.shopify.com/store/YOUR-STORE/settings/apps/development

---

## 3. Twitter / X Developer API

Required for: trend research (read) and sending DMs (write).

Where to get it:
  1. Go to https://developer.twitter.com/en/portal/dashboard
  2. Create a project + app (Free tier works for search; Basic tier needed for DMs)
  3. In your app settings → "Keys and tokens":
       - Copy "Bearer Token"                     → TWITTER_BEARER_TOKEN
       - Copy "API Key" and "API Key Secret"     → TWITTER_API_KEY / TWITTER_API_SECRET
  4. Under "Authentication tokens":
       - Generate "Access Token and Secret"      → TWITTER_ACCESS_TOKEN / TWITTER_ACCESS_TOKEN_SECRET
  5. Set app permissions to "Read and Write" (required for DMs)

Env vars to set:
    TWITTER_BEARER_TOKEN=AAAAAAA...
    TWITTER_API_KEY=xxxxxxxxxx
    TWITTER_API_SECRET=xxxxxxxxxx
    TWITTER_ACCESS_TOKEN=xxxxxxxxxx-xxxxxxxxxx
    TWITTER_ACCESS_TOKEN_SECRET=xxxxxxxxxx

Direct link:    https://developer.twitter.com/en/portal/dashboard

Note: Free tier has limited DM sends. Elevated access ($100/mo Basic plan) removes most limits.

---

## 4. Telegram Bot API

Required for: sending outreach DMs via Telegram.

Step 1 — Create your bot:
  1. Open Telegram, search @BotFather
  2. Send: /newbot
  3. Follow prompts → give it a name and username
  4. BotFather replies with your token: 123456789:ABCdef...

Step 2 — Get your Chat ID:
  1. Message your bot once (say hi)
  2. Open this URL in browser (replace TOKEN):
       https://api.telegram.org/bot{TOKEN}/getUpdates
  3. Find "chat" → "id" in the JSON response
  4. That number is your TELEGRAM_DEFAULT_CHAT_ID

     For group chats: add the bot to the group, send a message,
     then call getUpdates — the chat id will be negative (e.g., -1001234567890)

Env vars to set:
    TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
    TELEGRAM_DEFAULT_CHAT_ID=123456789        # your personal chat or a group/channel id

Direct link:    https://t.me/BotFather

---

## 5. iMessage (No Keys — macOS Only)

Required for: sending iMessage outreach DMs.

Setup:
  1. Open Messages.app on this Mac
  2. Sign in with your Apple ID (Preferences → iMessage → Sign In)
  3. Make sure iMessage is enabled and you can send messages
  4. That's it — AURA uses AppleScript to send via Messages.app

No env vars needed. Messages.app must be open and running.

To test manually:
    osascript -e 'tell application "Messages" to send "test" to buddy "+12025551234" of (first service whose service type is iMessage)'

---

## 6. Vhive API Key (Auto-Generated)

Required for: authenticating the Star-Office UI and API calls.

No action needed. On first server start, a key is auto-generated at:
    ~/.vhive/api_key

It prints to the terminal on startup. Paste it into the Star-Office login screen.

To use a custom key instead:
    VHIVE_API_KEY=your-custom-key-here    # set in .env

---

## 7. OpenHands (Optional)

Only needed if using a remote OpenHands agent server instead of local Docker sandbox.

    OPENHANDS_API_URL=http://localhost:3000    # or your remote URL

Direct link:    https://github.com/All-Hands-AI/OpenHands

---

## Setup Checklist

Copy and fill your .env:

    cp vhive_core/.env.example vhive_core/.env
    # then edit vhive_core/.env with the values above

Start Ollama:

    ollama serve

Start Vhive:

    source .venv/bin/activate
    python -m vhive_core.main --daemon    # 24/7 autonomous mode
    # or
    python -m vhive_core.main --server    # manual trigger only

Start the UI:

    cd star_office_ui/vhive-client
    npm run dev

Health check:

    curl http://localhost:8080/health

---

## Quick Reference

| Service   | Env Var(s)                                          | Required | Link                                      |
|-----------|-----------------------------------------------------|----------|-------------------------------------------|
| Shopify   | SHOPIFY_SHOP_DOMAIN, SHOPIFY_ACCESS_TOKEN           | Yes      | admin.shopify.com → Settings → Apps       |
| Twitter   | TWITTER_BEARER_TOKEN, API_KEY, ACCESS_TOKEN (+secrets) | Yes  | developer.twitter.com/en/portal/dashboard |
| Telegram  | TELEGRAM_BOT_TOKEN, TELEGRAM_DEFAULT_CHAT_ID        | Yes      | t.me/BotFather                            |
| iMessage  | (none)                                              | Yes*     | Messages.app → Sign in with Apple ID      |
| Ollama    | (none)                                              | Yes      | ollama.com/download                       |
| Vhive Key | VHIVE_API_KEY                                       | Auto     | Printed on server start                   |
| OpenHands | OPENHANDS_API_URL                                   | Optional | github.com/All-Hands-AI/OpenHands         |

* iMessage requires macOS with Messages.app signed in.
