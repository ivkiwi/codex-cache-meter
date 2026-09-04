---
name: cache-meter
description: Show cache hit rate, model/effort switch counts, estimated cache loss, API price equivalents, natural reset times, banked reset-credit status, and the Tibo reset forecast. Use when the user invokes /cache-meter or asks for Codex cache, usage, banked resets, or Tibo reset metrics.
---

# Cache Meter

Resolve the absolute path of this installed `SKILL.md` and replace its filename with `scripts/cache_meter.py`. Never resolve the script relative to the task working directory or assume the plugin root is the working directory.

If `mcp__codex_app__get_usage_limits` is available, call it once and keep only each item’s `title`, `status`, and `expiresAt` from `rateLimitResetCredits.credits`. Never expose account or credit IDs. If the tool is unavailable, mark banked-reset status as unavailable; do not fall back to credentials, raw account APIs, or CodexBar.

Run the absolute script path once with `python3 ... --prime` as a separate tool call. After that call completes, run the absolute script path normally and return only the second call's stdout verbatim. Do not combine the two commands into one shell invocation: the tool-call boundary lets Codex CLI persist the first model segment's token count before the report scans local JSONL.

If arguments were supplied, append them only to the second command. The script may make one unauthenticated read-only GET to the fixed `https://codex-resets.com/api/v1/status` endpoint. Do not read `auth.json` or invoke CodexBar. If local session logs are unavailable, report the script error plainly.

After the unchanged script output, append `### Banked resets`. Render every returned credit as a separate bullet with its title, status, and own expiry in local time and the local IANA timezone, for example `- **Full reset** — available · expires **Mon 21 Sep 2026, 03:00** (Europe/Istanbul)`. Do not show an aggregate count or earliest-expiry summary. If there are no credits, write `No banked resets available.` If the usage tool was unavailable, write `Status unavailable in this client.` Do not add any other summary.
