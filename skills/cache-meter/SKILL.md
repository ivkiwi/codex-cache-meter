---
name: cache-meter
description: Show cache hit, cache miss, hit rate, effort-switch effects, natural reset times, and the Tibo global-reset forecast. Use when the user invokes /cache-meter or asks for Codex cache, usage, or Tibo reset metrics.
---

# Cache Meter

Resolve the absolute path of this installed `SKILL.md`, replace its filename with `scripts/cache_meter.py`, and run that absolute script path with `python3`. Never resolve the script relative to the task working directory or assume the plugin root is the working directory. Return stdout verbatim.

If arguments were supplied, append them to the command. The script may make one unauthenticated read-only GET to the fixed `https://codex-resets.com/api/v1/status` endpoint. Do not read `auth.json`, call Codex account APIs, invoke CodexBar, or report banked resets. If local session logs are unavailable, report the script error plainly.
