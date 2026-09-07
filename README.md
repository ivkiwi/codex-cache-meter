# Cache Meter

[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md)

**The cache remembers. Until you switch models.**

Cache Meter turns local Codex session logs into the report Codex forgot to put in one place: cache hits and misses, model/effort switch losses, recovery time, API-price equivalents, natural resets, and the optional Tibo global-reset crystal ball.

When a switch knocks the cache cold, Cache Meter estimates how many cached tokens vanished and what the same traffic would cost at public API list prices. If the dollar figure looks like a small infrastructure budget, breathe: it is an API equivalent, not your Codex bill. One command, local JSONL, no dashboard safari, no account API, no Python dependencies.

## Full example report

Actual output from 7 September 2026 (Europe/Istanbul). Usage, prices, reset times, and forecasts are a historical snapshot.

## Cache Meter

`gpt-6-astra` · `medium` · local JSONL

| Scope | Input | Cache hit | Cache miss | Hit rate | Output | API equivalent |
|---|---:|---:|---:|---:|---:|---:|
| Latest request | 34.9K | 20.5K | 14.4K | **58.6%** | 221 | **$0.18** |
| Current task | 34.9K | 20.5K | 14.4K | **58.6%** | 221 | **$0.18** |
| Today | 135.24M | 128.59M | 6.65M | **95.1%** | 529.6K | **~$136.69** |
| Rolling 30 days | 6.65B | 6.40B | 255.14M | **96.2%** | 22.84M | **~$3508.79** |

Current model base prices: input **$10.00/MTok** · cached **$1.00/MTok** · output **$50.00/MTok**.

### Cache continuity

| Period | Switches | Drops ≥20 pp | Est. lost cache | API equivalent |
|---|---:|---:|---:|---:|
| Today | 3 | 3 | 362.7K | **$2.75** |
| Rolling 30 days | 39 | 37 | 4.87M | **$17.63** |

30-day split: **8** model changes · **34** effort changes · **2.7** calls average recovery among recovered drops.

Latest material drop: `gpt-5.6-sol/max` → `gpt-5.6-sol/high` · **96.0%** → **0.0%** (−96.0 pp) · recovered in **7** calls · **95.5K** estimated cached tokens lost · **$0.34** API equivalent.

Current task: Model/effort steady at `gpt-6-astra/medium`.

Scope API equivalents include cached input, cache misses, reported cache writes, output, and >272K long-context multipliers at public per-call model prices. `~` marks partial or inferred pricing. The continuity equivalent is only the uncached-vs-cached price gap caused by estimated cache loss. Neither is billed Codex spend; unknown models are excluded. Continuity excludes auto-review and subagent traffic.

### Rate-limit runway

| Window | Used | Natural reset |
|---|---|---|
| 5 hours | — | Not exposed |
| Week | 10% [#-----------] | Mon 14 Sep, 09:46 |

### Tibo

**Next reset:** 45% · elevated · within 24h · until Mon 07 Sep, 23:09

> @Gelassoldat @rezoundous Who says it won't reset in a while 👀

Source: [@thsottiaux](https://x.com/thsottiaux/status/2096692394435752258)

**Banked reset announced:** Sat 05 Sep, 03:39 · [@thsottiaux](https://x.com/thsottiaux/status/2096035437299237298)

> Because we are beyond happy to have Astra rolled out today ahead of schedule and you have been super patient with us \(not really, but it’s ok\!\)… we will do the full banked reset today too for all Plus, Pro and Business users&#46; Lands end of day&#46; Happy Astra day and enjoy a phenomenal weekend&#46; PS&#58; If you create the account or upgrade before 8pm PT you will get it too&#46; Still time\!

### Banked resets

- **Full reset** — available · expires **Mon 21 Sep 2026, 03:00** (Europe/Istanbul)
- **Full reset** — available · expires **Sun 04 Oct 2026, 04:58** (Europe/Istanbul)
- **Full reset** — available · expires **Mon 05 Oct 2026, 07:18** (Europe/Istanbul)

---

## What it shows

- Latest request, current task, today, and rolling 30-day cache metrics.
- Counts of model and reasoning-effort switches, material cache drops, estimated lost cached tokens, and recovery calls.
- Full API-equivalent cost for each scope, including cached input, cache misses, reported cache writes, output, and >272K long-context multipliers at each call's public model price.
- Cache-loss API equivalent using only the uncached-vs-cached input price gap for recognized models, including GPT-6 Astra.
- Natural 5-hour and weekly reset times when Codex exposes them.
- Every available banked reset with its own expiry in Codex App.
- An optional third-party Tibo reset forecast from `codex-resets.com`.

The dollar figures are API list-price equivalents, not billed Codex subscription spend. Unknown models are excluded from dollar estimates; partial or inferred estimates are prefixed with `~`. When available, Cache Meter reads the same auto-refreshed `models.dev` catalog cached by CodexBar and used by TimeGate, so new models and price changes require no plugin release. Bundled prices, including GPT-6 Astra, are the offline fallback and follow the [official OpenAI model comparison](https://developers.openai.com/api/docs/models/compare).

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

The Python meter reads local JSONL session files under `$CODEX_HOME/sessions` (or `~/.codex/sessions`) and, when present, CodexBar's local model-pricing cache. It does not invoke CodexBar or access Codex credentials or account APIs. In Codex App, the skill uses its built-in read-only usage-limits tool for banked-reset status and omits account and credit IDs.

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
