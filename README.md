# Cache Meter

[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md)

**The cache remembers. Until you switch models.**

Cache Meter turns local Codex session logs into the report Codex forgot to put in one place: cache hits and misses, model/effort switch losses, recovery time, API-price equivalents, natural resets, and the optional Tibo global-reset crystal ball.

When a switch knocks the cache cold, Cache Meter estimates how many cached tokens vanished and what the same traffic would cost at public API list prices. If the dollar figure looks like a small infrastructure budget, breathe: it is an API equivalent, not your Codex bill. One command, local JSONL, no dashboard safari, no account API, no Python dependencies.

```text
| Scope           | Input | Cache hit | Cache miss | Hit rate | Output | API equivalent |
|-----------------|-------|-----------|------------|----------|--------|----------------|
| Latest request  | 33.2K | 32.5K     | 662        | 98.0%    | 1.2K   | $0.04          |
| Current task    | 98.8K | 81.2K     | 17.6K      | 82.1%    | 4.8K   | $0.20          |

| Period          | Switches | Drops ≥20 pp | Est. lost cache | API equivalent |
|-----------------|----------|--------------|-----------------|----------------|
| Today           | 2        | 2            | 139.2K          | $0.50          |
| Rolling 30 days | 12       | 11           | 1.37M           | $4.20          |
```

## What it shows

- Latest request, current task, today, and rolling 30-day cache metrics.
- Counts of model and reasoning-effort switches, material cache drops, estimated lost cached tokens, and recovery calls.
- Full API-equivalent cost for each scope, including cached input, cache misses, reported cache writes, output, and >272K long-context multipliers at each call's public model price.
- Cache-loss API equivalent using only the uncached-vs-cached input price gap for recognized GPT-5.6 models.
- Natural 5-hour and weekly reset times when Codex exposes them.
- Every available banked reset with its own expiry in Codex App.
- An optional third-party Tibo reset forecast from `codex-resets.com`.

The dollar figures are API list-price equivalents, not billed Codex subscription spend. Unknown models are excluded from dollar estimates; partial or inferred estimates are prefixed with `~`. Prices follow the [official OpenAI model comparison](https://developers.openai.com/api/docs/models/compare).

## Install

```sh
codex plugin marketplace add ivkiwi/codex-cache-meter
codex plugin add cache-meter@cache-meter
```

Then run:

```text
/cache-meter
```

Skip the public forecast request with:

```text
/cache-meter --no-tibo
```

## Privacy

The Python meter reads local JSONL session files under `$CODEX_HOME/sessions` (or `~/.codex/sessions`) and does not access Codex credentials or account APIs. In Codex App, the skill uses its built-in read-only usage-limits tool for banked-reset status and omits account and credit IDs.

Unless `--no-tibo` is used, it makes one unauthenticated, read-only GET request to `https://codex-resets.com/api/v1/status`. The forecast is a third-party guess, not an OpenAI commitment.

## Requirements

- Codex App or CLI with local session logs.
- Python 3.10 or newer.
- No Python dependencies.

## Test

```sh
python3 -m unittest discover -s tests
```

## License

[MIT](LICENSE) · Built by Ivan & Ada.
