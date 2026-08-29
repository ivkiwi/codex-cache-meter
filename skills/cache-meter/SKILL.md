---
name: cache-meter
description: Show cache hit rate, model/effort switch counts, estimated cache loss, API price equivalents, natural reset times, and the Tibo global-reset forecast. Use when the user invokes /cache-meter or asks for Codex cache, usage, or Tibo reset metrics.
---

# Cache Meter

Resolve the absolute path of this installed `SKILL.md` and replace its filename with `scripts/cache_meter.py`. Never resolve the script relative to the task working directory or assume the plugin root is the working directory.

Run the absolute script path once with `python3 ... --prime` as a separate tool call. After that call completes, run the absolute script path normally and return only the second call's stdout verbatim. Do not combine the two commands into one shell invocation: the tool-call boundary lets Codex CLI persist the first model segment's token count before the report scans local JSONL.

If arguments were supplied, append them only to the second command. The script may make one unauthenticated read-only GET to the fixed `https://codex-resets.com/api/v1/status` endpoint. Do not read `auth.json`, call Codex account APIs, invoke CodexBar, or report banked resets. If local session logs are unavailable, report the script error plainly.
