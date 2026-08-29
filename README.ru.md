# Cache Meter

[English](README.md) · [Русский](README.ru.md)

**Хватит гадать, куда делся кэш. Измерь.**

Cache Meter — локальный плагин для Codex App и CLI. Он превращает session logs в короткий отчёт: попадания и промахи кэша, стоимость смены модели/effort, сроки сброса лимитов и опциональный прогноз глобального сброса от Tibo.

Если переключение модели или effort выбило кэш из-под ног, Cache Meter оценит, сколько cached tokens улетело и во что тот же трафик обошёлся бы по публичным API-тарифам. Одна команда, локальный JSONL, никаких дешбордов, API аккаунта и Python-зависимостей.

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

## Что показывает

- Метрики кэша для последнего запроса, текущей задачи, сегодняшнего дня и последних 30 дней.
- Количество смен модели и reasoning effort, существенные падения кэша, оценку потерянных cached tokens и число вызовов до восстановления.
- Полный API-эквивалент каждого scope: cached input, cache misses, известные cache writes, output и long-context множители для запросов больше 272K по публичной цене модели каждого вызова.
- API-эквивалент потери кэша только по разнице цен uncached/cached input для распознанных моделей GPT-5.6.
- Естественное время сброса 5-часового и недельного лимитов, если Codex его отдал.
- Опциональный сторонний прогноз сброса Tibo с `codex-resets.com`.

Суммы в долларах — эквиваленты по публичным API-тарифам, а не списания с подписки Codex. Неизвестные модели не входят в денежную оценку; частичная или расчётная оценка помечается `~`. Цены сверяются с [официальным сравнением моделей OpenAI](https://developers.openai.com/api/docs/models/compare).

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

Cache Meter читает локальные JSONL-файлы из `$CODEX_HOME/sessions` (или `~/.codex/sessions`). Он не читает `auth.json`, не вызывает API аккаунта Codex, не запускает CodexBar и не показывает banked resets.

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
