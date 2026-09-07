# Cache Meter

[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md)

**Кэш всё помнит. Пока вы не переключили модель.**

Cache Meter превращает локальные session logs в отчёт, который Codex забыл собрать в одном месте: попадания и промахи кэша, потери при смене модели/effort, время восстановления, API-эквиваленты, естественные сбросы лимитов и опциональный хрустальный шар Tibo.

Если переключение выбило кэш из-под ног, Cache Meter оценит, сколько cached tokens испарилось и во что тот же трафик превратился бы по публичным API-тарифам. Если сумма похожа на бюджет маленького дата-центра — выдохните: это API-эквивалент, а не счёт за Codex. Одна команда, локальный JSONL, никакого сафари по дешбордам, API аккаунта и Python-зависимостей.

## Полный пример отчёта

Реальный вывод от 7 сентября 2026 года (Europe/Istanbul). Расход, цены, сроки сбросов и прогнозы — исторический снимок.

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

## Что показывает

- Метрики кэша для последнего запроса, текущей задачи, сегодняшнего дня и последних 30 дней.
- Количество смен модели и reasoning effort, существенные падения кэша, оценку потерянных cached tokens и число вызовов до восстановления.
- Полный API-эквивалент каждого scope: cached input, cache misses, известные cache writes, output и long-context множители для запросов больше 272K по публичной цене модели каждого вызова.
- API-эквивалент потери кэша только по разнице цен uncached/cached input для распознанных моделей, включая GPT-6 Astra.
- Естественное время сброса 5-часового и недельного лимитов, если Codex его отдал.
- Каждый доступный banked reset с собственным сроком действия в Codex App.
- Опциональный сторонний прогноз сброса Tibo с `codex-resets.com`.

Суммы в долларах — эквиваленты по публичным API-тарифам, а не списания с подписки Codex. Неизвестные модели не входят в денежную оценку; частичная или расчётная оценка помечается `~`. Когда доступен CodexBar, Cache Meter читает тот же автоматически обновляемый каталог `models.dev`, который использует TimeGate: новые модели и изменения цен подхватываются без нового релиза плагина. Встроенные цены, включая GPT-6 Astra, остаются offline fallback и сверены с [официальным сравнением моделей OpenAI](https://developers.openai.com/api/docs/models/compare).

## Установка

```sh
codex plugin marketplace add ivkiwi/codex-cache-meter
codex plugin add cache-meter@cache-meter
```

Запуск:

```text
/cache-meter
```

Без запроса публичного прогноза:

```text
/cache-meter --no-tibo
```

## Приватность

Python-часть Cache Meter читает локальные JSONL-файлы сессий из `$CODEX_HOME/sessions` (или `~/.codex/sessions`) и, если он есть, локальный каталог цен CodexBar. Она не запускает CodexBar и не обращается к учётным данным или API аккаунта Codex. В Codex App skill получает статус banked resets через встроенный read-only tool лимитов и не показывает идентификаторы аккаунта или кредитов.

Без `--no-tibo` выполняется один неавторизованный read-only GET-запрос к `https://codex-resets.com/api/v1/status`. Это сторонний прогноз, а не обещание OpenAI.

## Требования

- Codex App или CLI с локальными session logs.
- Python 3.10 или новее.
- Python-зависимостей нет.

## Тест

```sh
python3 -m unittest discover -s tests
```

## Лицензия

[MIT](LICENSE) · Сделано Иваном и Адой.
