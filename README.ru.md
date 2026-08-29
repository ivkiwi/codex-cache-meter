# Cache Meter

[English](README.md) · [Русский](README.ru.md)

**Сначала посмотри, что Codex помнит, а потом ругай промпт.**

Cache Meter — локальный плагин для Codex. Он превращает session logs в короткий отчёт: попадания и промахи кэша, hit rate, непрерывность кэша при смене модели/effort, сроки сброса лимитов и опциональный прогноз глобального сброса от Tibo.

```text
| Scope           | Cache hit | Cache miss | Hit rate | Input |
|-----------------|-----------|------------|----------|-------|
| Latest request  | 32.5K     | 662        | 98.0%    | 33.2K |
| Current task    | 81.2K     | 17.6K      | 82.1%    | 98.8K |
```

## Что показывает

- Метрики кэша для последнего запроса, текущей задачи, сегодняшнего дня и последних 30 дней.
- Что произошло с кэшем после смены модели или reasoning effort.
- Естественное время сброса 5-часового и недельного лимитов, если Codex его отдал.
- Опциональный сторонний прогноз сброса Tibo с `codex-resets.com`.

## Установка

```sh
codex plugin marketplace add ivkiwi/cache-meter
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

- Codex с локальными session logs.
- Python 3.10 или новее.
- Python-зависимостей нет.

## Тест

```sh
python3 -m unittest discover -s tests
```

## Лицензия

[MIT](LICENSE) · Сделано Иваном и Адой.
