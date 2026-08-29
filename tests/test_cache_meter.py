import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/cache-meter/scripts/cache_meter.py"
SPEC = importlib.util.spec_from_file_location("cache_meter", SCRIPT)
cache_meter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cache_meter
SPEC.loader.exec_module(cache_meter)


class CacheMeterTest(unittest.TestCase):
    def test_prime_is_quiet_and_needs_no_sessions(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--prime", "--sessions", "/missing"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_render_and_source_allowlist(self):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        record = {
            "task_id": "task-1",
            "rollout_id": "rollout-1",
            "source": "vscode",
            "time": now,
            "model": "gpt-test",
            "effort": "high",
            "last": {"input_tokens": 100, "cached_input_tokens": 80, "cache_write_input_tokens": 0, "output_tokens": 10},
            "total": {"input_tokens": 250, "cached_input_tokens": 200, "cache_write_input_tokens": 0, "output_tokens": 25},
            "rate_limits": {},
        }
        data = {
            "records": [record],
            "contexts": [{**record, "turn_id": "turn-1"}],
            "thread_id": "task-1",
        }

        report = cache_meter.render(data, now)

        self.assertIn("| Latest request | 100 | 80 | 20 | **80.0%** | 10 | **—** |", report)
        self.assertIn("Model/effort steady at `gpt-test/high`.", report)
        self.assertIn("No active global-reset watch.", cache_meter.render(data, now, {}))
        terminal = cache_meter.terminal_report(report)
        self.assertIn("┌", terminal)
        self.assertIn("│ Latest request", terminal)
        self.assertNotIn("|---", terminal)
        self.assertIsNone(cache_meter.safe_source_link({"url": "https://example.com/nope"}))

        hostile = {
            "active_watch": {
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "reset_chance_percent": 75,
                "level": "strong\x1b]52;c;dGVzdA==\x07",
                "forecast_window": "soon\x9b31m",
                "text": "safe\x1b[2J text",
            }
        }
        hostile_report = cache_meter.render(data, now, hostile)
        hostile_terminal = cache_meter.terminal_report(hostile_report)
        for character in ("\x1b", "\x07", "\x9b"):
            self.assertNotIn(character, hostile_report)
            self.assertNotIn(character, hostile_terminal)

    def test_resumed_cli_rollout_is_included(self):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "2026/07/01/rollout-old-cli-task.jsonl"
            path.parent.mkdir(parents=True)
            events = [
                {
                    "timestamp": (now - timedelta(minutes=3)).isoformat(),
                    "type": "session_meta",
                    "payload": {"id": "old-cli-task", "session_id": "old-cli-task", "source": "cli"},
                },
                {
                    "timestamp": (now - timedelta(minutes=2)).isoformat(),
                    "type": "turn_context",
                    "payload": {"turn_id": "turn-1", "model": "gpt-5.6-sol", "effort": "high"},
                },
                {
                    "timestamp": (now - timedelta(minutes=1)).isoformat(),
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 80,
                                "cache_write_input_tokens": 0,
                                "output_tokens": 10,
                            },
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 80,
                                "cache_write_input_tokens": 0,
                                "output_tokens": 10,
                            },
                        },
                        "rate_limits": {},
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
            os.utime(path, (now.timestamp(), now.timestamp()))

            data = cache_meter.scan(root, now, None)

        self.assertEqual(data["thread_id"], "old-cli-task")
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["source"], "cli")

    def test_switch_loss_and_api_equivalent(self):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)

        def record(
            minutes,
            model,
            effort,
            cached,
            output=0,
            task="task-1",
            source="cli",
            input_tokens=1_000_000,
            cache_write=0,
        ):
            return {
                "task_id": task,
                "rollout_id": task,
                "source": source,
                "time": now + timedelta(minutes=minutes),
                "model": model,
                "effort": effort,
                "last": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "cache_write_input_tokens": cache_write,
                    "output_tokens": output,
                },
                "total": {},
                "rate_limits": {},
            }

        records = [
            record(-4, "gpt-5.6-sol", "high", 900_000),
            record(-3, "gpt-5.6-sol", "high", 900_000),
            record(-2, "gpt-5.6-sol", "max", 300_000),
            record(-1, "gpt-5.6-sol", "max", 880_000),
            record(-2, "codex-auto-review", "low", 100_000, task="review"),
            record(-1, "codex-auto-review", "high", 100_000, task="review"),
            record(-2, "gpt-5.6-sol", "low", 100_000, task="agent", source="subagent"),
            record(-1, "gpt-5.6-sol", "high", 100_000, task="agent", source="subagent"),
        ]

        events = cache_meter.switch_events(records)
        summary = cache_meter.summarize_switches(events, now - timedelta(days=1))

        self.assertEqual(len(events), 1)
        self.assertEqual(summary["switches"], 1)
        self.assertEqual(summary["effort_switches"], 1)
        self.assertEqual(summary["drops"], 1)
        self.assertEqual(summary["lost_tokens"], 620_000)
        self.assertEqual(summary["average_recovery_calls"], 2)
        self.assertEqual(cache_meter.api_equivalent_text(summary), "$4.46")
        self.assertIn("$4.46", cache_meter.latest_drop_note(events[0]))

        unrecovered = {
            **events[0],
            "time": now,
            "recovered": False,
            "end_reason": "log_end",
            "recovery_calls": 9,
        }
        censored = cache_meter.summarize_switches([events[0], unrecovered], now - timedelta(days=1))
        self.assertEqual(censored["average_recovery_calls"], 2)
        self.assertIn("log end", cache_meter.latest_drop_note(unrecovered))

        usage_equivalent = cache_meter.usage_api_equivalent([
            record(0, "gpt-5.6-sol", "max", 0, output=100_000, input_tokens=300_000),
        ])
        self.assertEqual(
            cache_meter.money_equivalent(
                usage_equivalent["value"],
                usage_equivalent["priced_tokens"],
                usage_equivalent["total_tokens"],
                usage_equivalent["estimated"],
            ),
            "$5.40",
        )

        cache_write_equivalent = cache_meter.usage_api_equivalent([
            record(0, "gpt-5.6-sol", "max", 80_000, input_tokens=100_000, cache_write=10_000),
        ])
        self.assertEqual(
            cache_meter.money_equivalent(
                cache_write_equivalent["value"],
                cache_write_equivalent["priced_tokens"],
                cache_write_equivalent["total_tokens"],
                cache_write_equivalent["estimated"],
            ),
            "$0.12",
        )

        missing_write = record(0, "gpt-5.6-sol", "max", 80_000, input_tokens=100_000)
        del missing_write["last"]["cache_write_input_tokens"]
        inferred = cache_meter.usage_api_equivalent([missing_write])
        self.assertEqual(
            cache_meter.money_equivalent(
                inferred["value"], inferred["priced_tokens"], inferred["total_tokens"], inferred["estimated"]
            ),
            "~$0.11",
        )


if __name__ == "__main__":
    unittest.main()
