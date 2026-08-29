import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/cache-meter/scripts/cache_meter.py"
SPEC = importlib.util.spec_from_file_location("cache_meter", SCRIPT)
cache_meter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cache_meter
SPEC.loader.exec_module(cache_meter)


class CacheMeterTest(unittest.TestCase):
    def test_render_and_source_allowlist(self):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        record = {
            "task_id": "task-1",
            "rollout_id": "rollout-1",
            "source": "vscode",
            "time": now,
            "model": "gpt-test",
            "effort": "high",
            "last": {"input_tokens": 100, "cached_input_tokens": 80},
            "total": {"input_tokens": 250, "cached_input_tokens": 200},
            "rate_limits": {},
        }
        data = {
            "records": [record],
            "contexts": [{**record, "turn_id": "turn-1"}],
            "thread_id": "task-1",
        }

        report = cache_meter.render(data, now)

        self.assertIn("| Latest request | 80 | 20 | **80.0%** | 100 |", report)
        self.assertIn("Model/effort steady at `gpt-test/high`.", report)
        self.assertIsNone(cache_meter.safe_source_link({"url": "https://example.com/nope"}))


if __name__ == "__main__":
    unittest.main()
