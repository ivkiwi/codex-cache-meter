#!/usr/bin/env python3
"""Read-only Codex cache and rate-limit report from local rollout JSONL."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TIBO_STATUS_URL = "https://codex-resets.com/api/v1/status"
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def token_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


@dataclass
class Usage:
    input: int = 0
    cached: int = 0
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
    return files


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
        candidates = [record for record in records if record["source"] == "vscode"]
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
    return " ".join(str(value or "").split())


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
        headers={"Accept": "application/json", "User-Agent": "cache-meter/0.1.5"},
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
        return []
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
        return []

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


def usage_row(label: str, usage: Usage) -> str:
    return (
        f"| {label} | {human_tokens(usage.cached)} | {human_tokens(usage.miss)} | "
        f"**{usage.hit_rate:.1f}%** | {human_tokens(usage.input)} |"
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
        if record["source"] == "vscode"
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
    today = period_usage(records, today_start)
    rolling = period_usage(records, now - timedelta(days=30))
    model = (latest or {}).get("model", "unknown")
    effort = (latest or {}).get("effort", "unknown")
    current_contexts = [
        context for context in data["contexts"]
        if context["source"] == "vscode"
        and (context["task_id"] == thread_id or context["rollout_id"] == thread_id)
    ]
    if not current_contexts:
        current_contexts = [
            context for context in data["contexts"]
            if context["task_id"] == thread_id or context["rollout_id"] == thread_id
        ]

    lines = [
        "## Cache Meter",
        "",
        f"`{model}` · `{effort}` · local JSONL",
        "",
        "| Scope | Cache hit | Cache miss | Hit rate | Input |",
        "|---|---:|---:|---:|---:|",
        usage_row("Latest request", request),
        usage_row("Current task", task),
        usage_row("Today", today),
        usage_row("Rolling 30 days", rolling),
        "",
        "### Cache continuity",
        "",
        effort_note(current_contexts, nonzero),
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
    parser.add_argument("--no-tibo", action="store_true", help="skip the public Tibo forecast request")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()
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
    print(render(data, now, status, error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
