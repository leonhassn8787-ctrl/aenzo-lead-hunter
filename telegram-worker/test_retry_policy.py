"""Regression tests for Telegram FloodWait retry timing."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

WORKER = Path(__file__).with_name("worker.py")


def load_retry_helper():
    tree = ast.parse(WORKER.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "retry_delay_seconds"
    )
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace["retry_delay_seconds"]


class TelegramRetryPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retry_delay = staticmethod(load_retry_helper())

    def test_respects_long_floodwait_instead_of_retrying_early(self):
        self.assertEqual(self.retry_delay(SimpleNamespace(seconds=1800)), 1805)

    def test_adds_safety_margin_to_floodwait(self):
        self.assertEqual(self.retry_delay(SimpleNamespace(seconds=120)), 125)

    def test_short_or_zero_floodwait_uses_minimum_backoff(self):
        self.assertEqual(self.retry_delay(SimpleNamespace(seconds=0)), 30)
        self.assertEqual(self.retry_delay(SimpleNamespace(seconds=1)), 30)

    def test_non_floodwait_errors_use_sixty_second_backoff(self):
        self.assertEqual(self.retry_delay(RuntimeError("temporary failure")), 60)

    def test_invalid_wait_value_falls_back_safely(self):
        self.assertEqual(self.retry_delay(SimpleNamespace(seconds="unknown")), 60)

    def test_worker_uses_the_shared_retry_policy(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("retry_after = retry_delay_seconds(exc)", source)
        self.assertNotIn("min(int(getattr(exc, \"seconds\", 60) or 60), 900)", source)


if __name__ == "__main__":
    unittest.main()
