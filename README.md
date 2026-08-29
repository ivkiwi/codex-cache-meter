# Cache Meter

[English](README.md) · [Русский](README.ru.md)

**See what Codex remembers before you blame the prompt.**

Cache Meter is a local-first Codex plugin that turns session logs into a compact report: cache hits and misses, hit rate, model/effort continuity, rate-limit resets, and the optional Tibo global-reset forecast.

```text
| Scope           | Cache hit | Cache miss | Hit rate | Input |
|-----------------|-----------|------------|----------|-------|
| Latest request  | 32.5K     | 662        | 98.0%    | 33.2K |
| Current task    | 81.2K     | 17.6K      | 82.1%    | 98.8K |
```

## What it shows

- Latest request, current task, today, and rolling 30-day cache metrics.
- Cache continuity across model and reasoning-effort changes.
- Natural 5-hour and weekly reset times when Codex exposes them.
- An optional third-party Tibo reset forecast from `codex-resets.com`.

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

Cache Meter reads local JSONL files under `$CODEX_HOME/sessions` (or `~/.codex/sessions`). It does not read `auth.json`, call Codex account APIs, invoke CodexBar, or report banked resets.

Unless `--no-tibo` is used, it makes one unauthenticated, read-only GET request to `https://codex-resets.com/api/v1/status`. The forecast is a third-party guess, not an OpenAI commitment.

## Requirements

- Codex with local session logs.
- Python 3.10 or newer.
- No Python dependencies.

## Test

```sh
python3 -m unittest discover -s tests
```

## License

[MIT](LICENSE) · Built by Ivan & Ada.
