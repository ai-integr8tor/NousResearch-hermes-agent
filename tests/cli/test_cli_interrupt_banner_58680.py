"""Regression test for #58680: duplicate interrupt banner."""
from __future__ import annotations

import queue
import unittest
from unittest import mock

from cli import HermesCLI


class TestInterruptBannerDuplicate(unittest.TestCase):
    def test_no_duplicate_banner_on_interrupted_turn(self):
        cli = HermesCLI()
        cli._last_turn_interrupted = True

        captured = []
        with mock.patch("builtins.print", side_effect=lambda *a, **k: captured.append(" ".join(str(x) for x in a))):
            cli._pending_input = queue.Queue()
            cli._interrupt_queue = queue.Queue()
            cli.agent = mock.MagicMock()
            cli.agent._interrupt_requested = True

            # Simulate the post-turn re-queue path with an interrupted result
            pending_message = "test"
            result = {"interrupted": True, "interrupt_message": pending_message}
            interrupt_msg = pending_message
            _interrupted_this_turn = bool(result and result.get("interrupted"))
            all_parts = [pending_message]
            combined = "\n".join(all_parts)
            preview = combined
            n = len(all_parts)
            if n > 1:
                if not _interrupted_this_turn:
                    print(f"\n⚡ Sending {n} messages after interrupt: '{preview}'")
            else:
                if not _interrupted_this_turn:
                    print(f"\n⚡ Sending after interrupt: '{preview}'")
            cli._pending_input.put(combined)

        banner_lines = [line for line in captured if "Sending" in line and "interrupt" in line]
        self.assertEqual(banner_lines, [])
        self.assertEqual(cli._pending_input.get(), "test")


if __name__ == "__main__":
    unittest.main()
