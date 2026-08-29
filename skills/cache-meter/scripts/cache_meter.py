#!/usr/bin/env python3
"""Read-only Codex cache and rate-limit report from local rollout JSONL."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TIBO_STATUS_URL = "https://codex-resets.com/api/v1/status"
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
MATERIAL_DROP_PP = 20.0
RECOVERY_TOLERANCE_PP = 5.0
LONG_CONTEXT_THRESHOLD = 272_000
INTERACTIVE_SOURCES = frozenset({"vscode", "cli"})
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
API_PRICES_PER_MTOK = {
    "gpt-5.6-sol": {"input": 4.00, "cached": 0.40, "output": 20.00},
    "gpt-5.6-terra": {"input": 2.00, "cached": 0.20, "output": 12.00},
    "gpt-5.6-luna": {"input": 0.20, "cached": 0.02, "output": 1.20},
    "gpt-5.6": {"input": 4.00, "cached": 0.40, "output": 20.00},
}


def token_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


@dataclass
class Usage:
    input: int = 0
    cached: int = 0
    cache_write: int = 0
    output: int = 0

    @property
    def miss(self) -> int:
        return max(0, self.input - self.cached)

    @property
    def hit_rate(self) -> float:
        return 100 * self.cached / self.input if self.input else 0.0

    def add(self, raw: dict[str, Any] | None) -> None:
        raw = raw or {}
        if not isinstance(raw, dict):
            return
        self.input += token_int(raw.get("input_tokens"))
        self.cached += token_int(raw.get("cached_input_tokens"))
        self.cache_write += token_int(raw.get("cache_write_input_tokens"))
        self.output += token_int(raw.get("output_tokens"))

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "Usage":
        value = cls()
        value.add(raw)
        return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp has no UTC offset")
    return parsed


def human_tokens(value: int) -> str:
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1_000:.1f}K"
    if value < 1_000_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value / 1_000_000_000:.2f}B"


def bar(percent: float, width: int = 12) -> str:
    filled = min(width, max(0, round(percent * width / 100)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def rollout_files(root: Path, since: datetime) -> list[Path]:
    first_day = (since - timedelta(days=1)).date()
    files: list[Path] = []
    for path in root.glob("*/*/*/rollout-*.jsonl"):
        try:
            day = datetime(
                int(path.parents[2].name),
                int(path.parents[1].name),
                int(path.parent.name),
            ).date()
        except ValueError:
            continue
        if day >= first_day:
            files.append(path)
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except (OSError, OverflowError, ValueError):
            continue
        if modified >= since:
            files.append(path)
    return files


def is_interactive_source(source: Any) -> bool:
    return isinstance(source, str) and source in INTERACTIVE_SOURCES


def read_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "session_meta":
                    payload = event.get("payload") or {}
                    return payload if isinstance(payload, dict) else None
    except OSError:
        pass
    return None


def usage_vector(record: dict[str, Any]) -> tuple[int, ...]:
    return tuple(
        token_int(raw.get(field))
        for raw in (record["last"], record["total"])
        for field in TOKEN_FIELDS
    )


def copied_prefix_length(child: list[dict[str, Any]], parent: list[dict[str, Any]]) -> int:
    """Return the copied fork prefix; replay timestamps are intentionally ignored."""
    child_vectors = [usage_vector(record) for record in child]
    parent_vectors = [usage_vector(record) for record in parent]
    best = 0
    # ponytail: quadratic scan; index vectors if real rollout histories make this measurable.
    for start in range(len(parent_vectors)):
        length = 0
        while (
            length < len(child_vectors)
            and start + length < len(parent_vectors)
            and child_vectors[length] == parent_vectors[start + length]
        ):
            length += 1
        best = max(best, length)
        if best == len(child_vectors):
            break
    return best


def scan(root: Path, now: datetime, thread_id: str | None) -> dict[str, Any]:
    since = now - timedelta(days=30)
    files = rollout_files(root, since)
    metadata = {path: meta for path in files if (meta := read_meta(path))}
    known_ids = {str(meta.get("id") or "") for meta in metadata.values()}
    pending = {str(meta.get("forked_from_id") or "") for meta in metadata.values()} - known_ids - {""}
    while pending:
        parent_id = pending.pop()
        if not all(char.isalnum() or char in "-_" for char in parent_id):
            continue
        for path in root.glob(f"*/*/*/rollout-*{parent_id}.jsonl"):
            meta = read_meta(path)
            if not meta or str(meta.get("id") or "") != parent_id:
                continue
            metadata[path] = meta
            known_ids.add(parent_id)
            ancestor = str(meta.get("forked_from_id") or "")
            if ancestor and ancestor not in known_ids:
                pending.add(ancestor)
            break
    parent_by_rollout = {
        str(meta.get("id") or ""): str(meta.get("forked_from_id") or "")
        for meta in metadata.values()
    }
    seen_contexts: set[tuple[Any, ...]] = set()
    records_by_rollout: dict[str, list[dict[str, Any]]] = {}
    contexts: list[dict[str, Any]] = []

    for path, meta in metadata.items():
        task_id = str(meta.get("session_id") or meta.get("id") or "")
        rollout_id = str(meta.get("id") or "")
        parent_id = str(meta.get("forked_from_id") or "")
        source = meta.get("source")
        if isinstance(source, str):
            source_kind = source
        elif isinstance(source, dict) and isinstance(source.get("subagent"), dict):
            source_kind = next(iter(source["subagent"]), "subagent")
        else:
            source_kind = "unknown"
        model = "unknown"
        effort = "unknown"
        rollout_records: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("type")
                    payload = event.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    timestamp = event.get("timestamp")
                    if kind == "session_meta":
                        continue
                    if not rollout_id or not timestamp:
                        continue
                    try:
                        event_time = parse_time(str(timestamp))
                    except (TypeError, ValueError):
                        continue
                    if kind == "turn_context":
                        model = str(payload.get("model") or model)
                        effort = str(payload.get("effort") or effort)
                        key = (rollout_id, timestamp, payload.get("turn_id"), model, effort)
                        if key not in seen_contexts:
                            seen_contexts.add(key)
                            contexts.append({
                                "task_id": task_id,
                                "rollout_id": rollout_id,
                                "source": source_kind,
                                "time": event_time,
                                "turn_id": payload.get("turn_id"),
                                "model": model,
                                "effort": effort,
                            })
                        continue
                    if kind != "event_msg" or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info") or {}
                    if not isinstance(info, dict):
                        continue
                    total = info.get("total_token_usage") or {}
                    last = info.get("last_token_usage") or {}
                    total = total if isinstance(total, dict) else {}
                    last = last if isinstance(last, dict) else {}
                    rate_limits = payload.get("rate_limits") or {}
                    rollout_records.append({
                        "task_id": task_id,
                        "rollout_id": rollout_id,
                        "parent_id": parent_id,
                        "source": source_kind,
                        "time": event_time,
                        "model": model,
                        "effort": effort,
                        "last": last,
                        "total": total,
                        "rate_limits": rate_limits if isinstance(rate_limits, dict) else {},
                    })
        except OSError:
            continue
        records_by_rollout[rollout_id] = rollout_records

    records: list[dict[str, Any]] = []
    seen_records: set[tuple[Any, ...]] = set()
    for rollout_id, rollout_records in records_by_rollout.items():
        parent_id = parent_by_rollout.get(rollout_id, "")
        copied = copied_prefix_length(rollout_records, records_by_rollout.get(parent_id, []))
        for record in rollout_records[copied:]:
            key = (record["task_id"], record["time"], usage_vector(record))
            if key not in seen_records:
                seen_records.add(key)
                records.append(record)

    records.sort(key=lambda item: item["time"])
    contexts.sort(key=lambda item: item["time"])
    if not thread_id:
        candidates = [record for record in records if is_interactive_source(record["source"])]
        thread_id = candidates[-1]["task_id"] if candidates else None
    return {"records": records, "contexts": contexts, "thread_id": thread_id}


def period_usage(records: list[dict[str, Any]], start: datetime) -> Usage:
    result = Usage()
    for record in records:
        if record["time"] >= start:
            result.add(record["last"])
    return result


def effort_note(contexts: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    if not contexts:
        return "Model/effort data unavailable."
    changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
    previous = contexts[0]
    for current in contexts[1:]:
        if (current["model"], current["effort"]) != (previous["model"], previous["effort"]):
            changes.append((previous, current))
        previous = current
    latest_context = contexts[-1]
    if not changes:
        return f"Model/effort steady at `{latest_context['model']}/{latest_context['effort']}`."
    before, after = changes[-1]
    calls = [
        record for record in records
        if record["time"] >= after["time"] and token_int(record["last"].get("input_tokens")) > 0
    ]
    change = f"`{before['model']}/{before['effort']}` → `{after['model']}/{after['effort']}`"
    if not calls:
        return f"Model/effort changed {change}; no completed model call yet."
    cold = Usage.from_raw(calls[0]["last"])
    latest = Usage.from_raw(calls[-1]["last"])
    return (
        f"Model/effort changed {change}. "
        f"First call hit **{cold.hit_rate:.1f}%**; latest **{latest.hit_rate:.1f}%** "
        f"across {len(calls)} model call{'s' if len(calls) != 1 else ''}."
    )


def switch_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        usage = Usage.from_raw(record["last"])
        if (
            is_interactive_source(record["source"])
            and usage.input
            and record["model"] not in {"unknown", "codex-auto-review"}
            and record["effort"] != "unknown"
        ):
            by_task[record["task_id"]].append(record)

    events: list[dict[str, Any]] = []
    for task_records in by_task.values():
        task_records.sort(key=lambda item: item["time"])
        for index in range(1, len(task_records)):
            before = task_records[index - 1]
            after = task_records[index]
            old = (before["model"], before["effort"])
            new = (after["model"], after["effort"])
            if old == new:
                continue

            previous = [
                Usage.from_raw(item["last"]).hit_rate
                for item in task_records[max(0, index - 3):index]
                if (item["model"], item["effort"]) == old
            ]
            baseline = statistics.median(previous)
            first_hit = Usage.from_raw(after["last"]).hit_rate
            recovery: list[dict[str, Any]] = []
            losses: list[tuple[dict[str, Any], int]] = []
            recovered = False
            for candidate in task_records[index:]:
                if (candidate["model"], candidate["effort"]) != new:
                    break
                recovery.append(candidate)
                usage = Usage.from_raw(candidate["last"])
                losses.append((candidate, max(0, round(usage.input * baseline / 100) - usage.cached)))
                if Usage.from_raw(candidate["last"]).hit_rate >= baseline - RECOVERY_TOLERANCE_PP:
                    recovered = True
                    break

            lost = sum(loss for _, loss in losses)
            premium = api_cache_premium(new[0])
            priced_tokens = lost if premium is not None else 0
            api_equivalent = sum(
                loss * premium * input_price_multiplier(Usage.from_raw(item["last"]).input) / 1_000_000
                for item, loss in losses
            ) if premium is not None else 0.0
            events.append({
                "time": after["time"],
                "from_model": old[0],
                "from_effort": old[1],
                "to_model": new[0],
                "to_effort": new[1],
                "baseline_hit": baseline,
                "first_hit": first_hit,
                "drop_pp": max(0.0, baseline - first_hit),
                "lost_tokens": lost,
                "priced_tokens": priced_tokens,
                "api_equivalent": api_equivalent,
                "recovery_calls": len(recovery),
                "recovered": recovered,
                "end_reason": (
                    "recovered"
                    if recovered
                    else "next_switch"
                    if index + len(recovery) < len(task_records)
                    else "log_end"
                ),
                "model_changed": old[0] != new[0],
                "effort_changed": old[1] != new[1],
            })
    return sorted(events, key=lambda event: event["time"])


def api_prices(model: str) -> dict[str, float] | None:
    for name in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        if model == name or model.startswith(f"{name}-"):
            return API_PRICES_PER_MTOK[name]
    return API_PRICES_PER_MTOK.get(model)


def api_cache_premium(model: str) -> float | None:
    prices = api_prices(model)
    return prices["input"] - prices["cached"] if prices else None


def input_price_multiplier(input_tokens: int) -> float:
    return 2.0 if input_tokens > LONG_CONTEXT_THRESHOLD else 1.0


def output_price_multiplier(input_tokens: int) -> float:
    return 1.5 if input_tokens > LONG_CONTEXT_THRESHOLD else 1.0


def usage_api_equivalent(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_tokens = 0
    priced_tokens = 0
    value = 0.0
    estimated = False
    for record in records:
        raw = record["last"] if isinstance(record.get("last"), dict) else {}
        usage = Usage.from_raw(raw)
        tokens = usage.input + usage.output
        total_tokens += tokens
        if (prices := api_prices(record["model"])) is None:
            continue
        priced_tokens += tokens
        cache_write_raw = raw.get("cache_write_input_tokens")
        cache_write_known = isinstance(cache_write_raw, int) and not isinstance(cache_write_raw, bool) and cache_write_raw >= 0
        cache_write = min(usage.miss, usage.cache_write) if cache_write_known else 0
        if usage.miss and not cache_write_known:
            estimated = True
        input_multiplier = input_price_multiplier(usage.input)
        value += (
            (
                (usage.miss - cache_write) * prices["input"]
                + cache_write * prices["input"] * 1.25
                + usage.cached * prices["cached"]
            ) * input_multiplier
            + usage.output * prices["output"] * output_price_multiplier(usage.input)
        ) / 1_000_000
    return {
        "value": value,
        "priced_tokens": priced_tokens,
        "total_tokens": total_tokens,
        "estimated": estimated,
    }


def money_equivalent(value: float, priced_tokens: int, total_tokens: int, estimated: bool = False) -> str:
    if total_tokens and not priced_tokens:
        return "—"
    prefix = "~" if estimated or priced_tokens < total_tokens else ""
    return f"{prefix}${value:.2f}"


def summarize_switches(events: list[dict[str, Any]], start: datetime) -> dict[str, Any]:
    scoped = [event for event in events if event["time"] >= start]
    drops = [event for event in scoped if event["drop_pp"] >= MATERIAL_DROP_PP]
    recovered = [event for event in drops if event["recovered"]]
    return {
        "switches": len(scoped),
        "model_switches": sum(event["model_changed"] for event in scoped),
        "effort_switches": sum(event["effort_changed"] for event in scoped),
        "drops": len(drops),
        "lost_tokens": sum(event["lost_tokens"] for event in drops),
        "priced_tokens": sum(event["priced_tokens"] for event in drops),
        "api_equivalent": sum(event["api_equivalent"] for event in drops),
        "average_recovery_calls": statistics.mean(event["recovery_calls"] for event in recovered) if recovered else None,
        "latest": drops[-1] if drops else None,
    }


def api_equivalent_text(summary: dict[str, Any]) -> str:
    return money_equivalent(summary["api_equivalent"], summary["priced_tokens"], summary["lost_tokens"])


def continuity_row(label: str, summary: dict[str, Any]) -> str:
    return (
        f"| {label} | {summary['switches']} | {summary['drops']} | "
        f"{human_tokens(summary['lost_tokens'])} | **{api_equivalent_text(summary)}** |"
    )


def latest_drop_note(event: dict[str, Any] | None) -> str:
    if event is None:
        return "Latest material drop: none in this period."
    change = (
        f"`{event['from_model']}/{event['from_effort']}` → "
        f"`{event['to_model']}/{event['to_effort']}`"
    )
    recovery = (
        f"recovered in **{event['recovery_calls']}** calls"
        if event["recovered"]
        else f"not recovered before the next switch ({event['recovery_calls']} calls observed)"
        if event["end_reason"] == "next_switch"
        else f"not yet recovered at log end ({event['recovery_calls']} calls observed)"
    )
    equivalent = (
        f"**${event['api_equivalent']:.2f}** API equivalent"
        if event["priced_tokens"] else "API equivalent unavailable"
    )
    return (
        f"Latest material drop: {change} · **{event['baseline_hit']:.1f}%** → "
        f"**{event['first_hit']:.1f}%** (−{event['drop_pp']:.1f} pp) · {recovery} · "
        f"**{human_tokens(event['lost_tokens'])}** estimated cached tokens lost · {equivalent}."
    )


def rate_rows(rate_limits: dict[str, Any], now: datetime) -> list[tuple[str, str, str]]:
    limits = [value for key in ("primary", "secondary") if isinstance((value := rate_limits.get(key)), dict)]
    by_window: dict[int, dict[str, Any]] = {}
    for value in limits:
        try:
            by_window[int(value.get("window_minutes") or 0)] = value
        except (TypeError, ValueError):
            continue
    rows: list[tuple[str, str, str]] = []
    for minutes, label in ((300, "5 hours"), (10080, "Week")):
        value = by_window.get(minutes)
        if not value:
            rows.append((label, "—", "Not exposed"))
            continue
        try:
            used = float(value.get("used_percent") or 0)
            reset_at = int(value.get("resets_at") or 0)
        except (TypeError, ValueError):
            rows.append((label, "—", "Not exposed"))
            continue
        if not math.isfinite(used):
            rows.append((label, "—", "Not exposed"))
            continue
        used = max(0, min(100, used))
        try:
            reset = datetime.fromtimestamp(reset_at, timezone.utc) if reset_at else None
        except (OSError, OverflowError, ValueError):
            rows.append((label, "—", "Not exposed"))
            continue
        reset_text = reset.astimezone().strftime("%a %d %b, %H:%M") if reset else "—"
        rows.append((label, f"{used:.0f}% {bar(used)}", "Reset due" if reset and reset <= now else reset_text))
    return rows


def compact(value: Any) -> str:
    return " ".join(CONTROL_CHARACTERS.sub(" ", str(value or "")).split())


def markdown_text(value: Any) -> str:
    text = html.escape(compact(value), quote=False)
    for character in "\\*_{}[]()#+-!|>~":
        text = text.replace(character, f"\\{character}")
    return text.replace("`", "&#96;").replace(":", "&#58;").replace(".", "&#46;")


def reset_details(value: Any) -> tuple[str, list[str]]:
    raw = str(value or "")
    paragraphs = [compact(paragraph) for paragraph in raw.split("\n\n") if compact(paragraph)]
    preview = " ".join(paragraphs[:3])
    if len(preview) > 600:
        preview = preview[:597].rsplit(" ", 1)[0] + "..."
    fixes = []
    for line in raw.splitlines():
        if line.startswith("- ") and (name := line[2:].split(".", 1)[0].strip()):
            fixes.append(markdown_text(name))
    return markdown_text(preview), fixes[:12]


def safe_source_link(source: Any) -> str | None:
    if not isinstance(source, dict):
        return None
    url = str(source.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return None
    author = markdown_text(source.get("author") or "source")
    safe_url = urllib.parse.quote(url, safe=":/?&=%#@+,-._~")
    return f"[@{author.lstrip('@')}]({safe_url})"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, file_pointer: Any, code: int, message: str, headers: Any, new_url: str) -> None:
        return None


def fetch_tibo_status() -> dict[str, Any]:
    request = urllib.request.Request(
        TIBO_STATUS_URL,
        headers={"Accept": "application/json", "User-Agent": "cache-meter/0.2.1"},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
        raw = response.read(262_145)
    if len(raw) > 262_144:
        raise ValueError("forecast response is too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("forecast response is not an object")
    return value


def tibo_section(status: dict[str, Any] | None, now: datetime, error: str | None = None) -> list[str]:
    if status is None:
        if error == "disabled":
            return []
        return ["### Tibo", "", "Forecast unavailable."]
    if isinstance(status.get("data"), dict):
        status = status["data"]

    watch = status.get("active_watch")
    if not isinstance(watch, dict):
        watch = None
    expires = None
    if watch and watch.get("expires_at"):
        try:
            expires = parse_time(str(watch["expires_at"]))
        except ValueError:
            pass
    if not expires or expires <= now:
        watch = None

    latest = status.get("latest_reset")
    has_latest = isinstance(latest, dict) and latest.get("announced_at")
    if not watch and not has_latest:
        return ["### Tibo", "", "No active global-reset watch."]

    lines = ["### Tibo", ""]
    if watch:
        try:
            chance = max(0, min(100, int(watch.get("reset_chance_percent") or 0)))
        except (TypeError, ValueError):
            chance = 0
        level = markdown_text(watch.get("level") or "unknown")
        window = markdown_text(watch.get("forecast_window") or "window unknown")
        until = expires.astimezone().strftime("%a %d %b, %H:%M")
        lines.append(f"**Next reset:** {chance}% · {level} · {window} · until {until}")
        if text := markdown_text(watch.get("text")):
            lines.extend(["", f"> {text}"])
        if link := safe_source_link(watch.get("source")):
            lines.extend(["", f"Source: {link}"])

    if has_latest:
        try:
            announced = parse_time(str(latest["announced_at"])).astimezone().strftime("%a %d %b, %H:%M")
            suffix = f" · {link}" if (link := safe_source_link(latest.get("source"))) else ""
            lines.extend(["", f"**Global reset announced:** {announced}{suffix}"])
            preview, fixes = reset_details(latest.get("text"))
            if preview:
                lines.extend(["", f"> {preview}"])
            if fixes:
                lines.extend(["", f"Fixes: {', '.join(fixes)}."])
        except ValueError:
            pass
    return lines


def usage_row(label: str, usage: Usage, equivalent: dict[str, Any]) -> str:
    return (
        f"| {label} | {human_tokens(usage.input)} | {human_tokens(usage.cached)} | "
        f"{human_tokens(usage.miss)} | **{usage.hit_rate:.1f}%** | {human_tokens(usage.output)} | "
        f"**{money_equivalent(equivalent['value'], equivalent['priced_tokens'], equivalent['total_tokens'], equivalent['estimated'])}** |"
    )


def render(
    data: dict[str, Any],
    now: datetime,
    tibo_status: dict[str, Any] | None = None,
    tibo_error: str | None = None,
) -> str:
    records = data["records"]
    thread_id = data["thread_id"]
    current = [
        record for record in records
        if is_interactive_source(record["source"])
        and (record["task_id"] == thread_id or record["rollout_id"] == thread_id)
    ]
    if not current:
        current = [
            record for record in records
            if record["task_id"] == thread_id or record["rollout_id"] == thread_id
        ]
    nonzero = [record for record in current if token_int(record["last"].get("input_tokens")) > 0]
    latest = current[-1] if current else None
    request = Usage.from_raw(nonzero[-1]["last"] if nonzero else None)
    task = Usage.from_raw(latest["total"] if latest else None)
    local_now = now.astimezone()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_records = [record for record in records if record["time"] >= today_start]
    rolling_records = [record for record in records if record["time"] >= now - timedelta(days=30)]
    today = period_usage(records, today_start)
    rolling = period_usage(records, now - timedelta(days=30))
    model = (latest or {}).get("model", "unknown")
    effort = (latest or {}).get("effort", "unknown")
    current_contexts = [
        context for context in data["contexts"]
        if is_interactive_source(context["source"])
        and (context["task_id"] == thread_id or context["rollout_id"] == thread_id)
    ]
    if not current_contexts:
        current_contexts = [
            context for context in data["contexts"]
            if context["task_id"] == thread_id or context["rollout_id"] == thread_id
        ]

    events = switch_events(records)
    today_switches = summarize_switches(events, today_start)
    rolling_switches = summarize_switches(events, now - timedelta(days=30))
    request_equivalent = usage_api_equivalent(nonzero[-1:] if nonzero else [])
    task_equivalent = usage_api_equivalent(current)
    today_equivalent = usage_api_equivalent(today_records)
    rolling_equivalent = usage_api_equivalent(rolling_records)
    current_prices = api_prices(model)

    lines = [
        "## Cache Meter",
        "",
        f"`{model}` · `{effort}` · local JSONL",
        "",
        "| Scope | Input | Cache hit | Cache miss | Hit rate | Output | API equivalent |",
        "|---|---:|---:|---:|---:|---:|---:|",
        usage_row("Latest request", request, request_equivalent),
        usage_row("Current task", task, task_equivalent),
        usage_row("Today", today, today_equivalent),
        usage_row("Rolling 30 days", rolling, rolling_equivalent),
        "",
        (
            f"Current model base prices: input **${current_prices['input']:.2f}/MTok** · "
            f"cached **${current_prices['cached']:.2f}/MTok** · "
            f"output **${current_prices['output']:.2f}/MTok**."
            if current_prices else "Current model base prices: unavailable."
        ),
        "",
        "### Cache continuity",
        "",
        "| Period | Switches | Drops ≥20 pp | Est. lost cache | API equivalent |",
        "|---|---:|---:|---:|---:|",
        continuity_row("Today", today_switches),
        continuity_row("Rolling 30 days", rolling_switches),
        "",
        (
            f"30-day split: **{rolling_switches['model_switches']}** model changes · "
            f"**{rolling_switches['effort_switches']}** effort changes · "
            f"**{rolling_switches['average_recovery_calls']:.1f}** calls average recovery among recovered drops."
            if rolling_switches["average_recovery_calls"] is not None
            else "Average recovery: **—** (no recovered material drops in this period)."
        ),
        "",
        latest_drop_note(rolling_switches["latest"]),
        "",
        f"Current task: {effort_note(current_contexts, nonzero)}",
        "",
        (
            "Scope API equivalents include cached input, cache misses, reported cache writes, output, and "
            ">272K long-context multipliers at public per-call model prices. `~` marks partial or inferred pricing. "
            "The continuity equivalent is only the uncached-vs-cached price gap caused by estimated cache loss. "
            "Neither is billed Codex spend; unknown models are excluded. Continuity excludes auto-review and subagent traffic."
        ),
        "",
        "### Rate-limit runway",
        "",
        "| Window | Used | Natural reset |",
        "|---|---|---|",
    ]
    limits = (latest or {}).get("rate_limits", {})
    lines.extend(f"| {' | '.join(row)} |" for row in rate_rows(limits, now))
    lines.extend(["", *tibo_section(tibo_status, now, tibo_error)])
    return "\n".join(lines)


def terminal_color(text: str, code: str) -> str:
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"\033[{code}m{text}\033[0m"


def plain_markdown(text: str) -> str:
    text = CONTROL_CHARACTERS.sub("", html.unescape(text))
    text = re.sub(r"\[([^]]+)]\((https://[^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"\\([\\*_{}\[\]()#+\-!|>~])", r"\1", text)
    return text.replace("**", "").replace("`", "")


def terminal_table(lines: list[str]) -> list[str]:
    raw = [[plain_markdown(cell.strip()) for cell in line.strip().strip("|").split("|")] for line in lines]
    headers, separators, *rows = raw
    right = [separator.endswith(":") for separator in separators]
    widths = [max(len(row[index]) for row in [headers, *rows]) for index in range(len(headers))]

    def border(left: str, middle: str, right_edge: str) -> str:
        return left + middle.join("─" * (width + 2) for width in widths) + right_edge

    def row(cells: list[str]) -> str:
        values = [
            cell.rjust(width) if right[index] else cell.ljust(width)
            for index, (cell, width) in enumerate(zip(cells, widths))
        ]
        return "│ " + " │ ".join(values) + " │"

    return [
        terminal_color(border("┌", "┬", "┐"), "2"),
        terminal_color(row(headers), "1"),
        terminal_color(border("├", "┼", "┤"), "2"),
        *(row(cells) for cells in rows),
        terminal_color(border("└", "┴", "┘"), "2"),
    ]


def terminal_report(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|") and index + 1 < len(lines) and lines[index + 1].startswith("|---"):
            end = index + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            output.extend(terminal_table(lines[index:end]))
            index = end
            continue
        if line.startswith("## "):
            output.append(terminal_color(plain_markdown(line[3:]).upper(), "1;36"))
        elif line.startswith("### "):
            output.append(terminal_color(plain_markdown(line[4:]).upper(), "1;35"))
        elif line.startswith("> "):
            output.append(f"  {terminal_color('│', '2')} {plain_markdown(line[2:])}")
        else:
            output.append(plain_markdown(line))
        index += 1
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions",
        help="Codex sessions directory",
    )
    parser.add_argument(
        "--thread-id",
        default=os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"),
        help="Current Codex task id",
    )
    parser.add_argument("--prime", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-tibo", action="store_true", help="skip the public Tibo forecast request")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prime:
        return 0
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if not args.sessions.is_dir():
        parser.error(f"sessions directory not found: {args.sessions}")
    data = scan(args.sessions, now, args.thread_id)
    if not data["records"]:
        parser.error("no token_count records found in the last 30 days")
    status = None
    error = "disabled"
    if not args.no_tibo:
        try:
            status = fetch_tibo_status()
            error = None
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            error = str(exc)
    report = render(data, now, status, error)
    print(terminal_report(report) if sys.stdout.isatty() else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
