---
description: 'Telegram Bot API sendMessage facts for workflow failure notifications — endpoint shape with token placement, required chat_id/text params, and the ok:false JSON error contract.'
---

# Telegram Bot API — sendMessage

Curated from the official Telegram Bot API reference (core.telegram.org/bots/api)
for the `verifiable-deploy-chain` work: the reconcile workflow posts failure
notifications through this method.

## Contract

- Endpoint: `https://api.telegram.org/bot<token>/sendMessage` — the bot token is
  a **path segment** after the literal `bot` prefix (treat the full URL as a
  credential; never echo it into logs).
- Required parameters: `chat_id` (destination chat identifier) and `text`
  (UTF-8 message). GET and POST are both accepted; parameters may be sent as
  query string, form-encoded, or JSON.
- Success returns `{"ok": true, "result": {...}}`; failure returns
  `{"ok": false, "error_code": ..., "description": "..."}` — an HTTP-level
  check alone can miss `ok: false` bodies, so `curl -f` plus a non-2xx status
  is the minimal failure signal for notification delivery.
- The token is issued by BotFather at bot creation; the `chat_id` for a private
  operator chat is discovered from the bot's incoming updates (`getUpdates`)
  after the operator messages the bot once.

## Sources

- https://core.telegram.org/bots/api#sendmessage
