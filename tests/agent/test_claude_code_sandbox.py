"""E4 (933c653bd) regression: SANDBOX_PRESETS cron_no_workdir merged into
primary_minus_memory. Verify component uniqueness and preset resolution
changes since the merge.

Design note: SANDBOX_PRESETS values are SandboxComponents dataclasses
(not dicts with a 'digest' key). The manifest digest is computed in
``_collect_manifest_inputs`` + ``_hash_inputs``, where the components
dict is folded in. Therefore, two presets with identical SandboxComponents
would produce identical manifest digests for any fixed hermes_home /
platform / model — which is the exact failure mode E4 fixed
(cron_no_workdir and primary_minus_memory had identical components,
leading to identical digests and a useless preset alias).

These tests guard the invariant: distinct presets must have distinct
SandboxComponents, _resolve_preset must not introduce a separate
cron_no_workdir mapping, and the merged (T, T, T) flag combo must
resolve to primary_minus_memory.
"""
import dataclasses
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.claude_code_sandbox import (
    SANDBOX_PRESETS,
    _collect_manifest_inputs,
    _hash_inputs,
    _resolve_preset,
)


class TestSandboxPresetsUniqueness(unittest.TestCase):
    def test_preset_component_digests_are_unique(self):
        """E4: every preset's SandboxComponents must hash to a distinct
        value. Otherwise the manifest cache could return a stale sandbox
        for the wrong preset (the original cron_no_workdir bug).

        We compute the digest using a hermes_home with no SOUL/memory/
        skills/config so the only variable that differs across presets
        is the components dict — isolating the invariant we care about.
        """
        with tempfile.TemporaryDirectory() as empty_home:
            digests = {}
            for name, components in SANDBOX_PRESETS.items():
                inputs = _collect_manifest_inputs(
                    hermes_home=Path(empty_home),
                    platform=None,
                    model=None,
                    components=components,
                )
                digests[name] = _hash_inputs(inputs)
        self.assertEqual(
            len(set(digests.values())), len(digests),
            f"Duplicate component-derived digests detected: {digests}",
        )

    def test_no_cron_no_workdir_preset_after_e4(self):
        """E4 merged cron_no_workdir into primary_minus_memory. If a
        future refactor re-adds it as a separate preset with the same
        components, this test fails and forces a re-review of the merge.
        """
        self.assertNotIn(
            "cron_no_workdir", SANDBOX_PRESETS,
            "cron_no_workdir was merged into primary_minus_memory in E4; "
            "re-add only with explicit caller and distinct components",
        )

    def test_cron_with_workdir_uses_primary_minus_memory(self):
        """E4: (F, T, T) — skip_context_files=False, load_soul_identity=True,
        skip_memory=True — cron with workdir — resolves to
        primary_minus_memory.
        """
        agent = SimpleNamespace(
            skip_context_files=False,
            load_soul_identity=True,
            skip_memory=True,
        )
        self.assertEqual(_resolve_preset(agent), "primary_minus_memory")

    def test_cron_no_workdir_flag_combo_resolves_to_primary_minus_memory(self):
        """E4: (T, T, T) — skip_context_files=True, load_soul_identity=True,
        skip_memory=True — cron without workdir — used to map to
        cron_no_workdir; now also resolves to primary_minus_memory since
        the merge produced an identical components hash.
        """
        agent = SimpleNamespace(
            skip_context_files=True,
            load_soul_identity=True,
            skip_memory=True,
        )
        self.assertEqual(_resolve_preset(agent), "primary_minus_memory")




# ===========================================================================
# B2 (b5a4dd6c1) — Iterable import regression guard
# B3 (b5a4dd6c1) — init channel branch regression guard
# ===========================================================================
class TestDeadCodeGrepRegression(unittest.TestCase):
    """Static-grep tests guarding against re-introduction of patterns
    removed in commit b5a4dd6c1. These catch the regression mode where
    a future contributor re-adds the patterns without a real caller."""

    def test_no_iterable_import_in_sandbox(self):
        """B2: `from typing import Iterable` was removed from sandbox
        because no SandboxComponents field used it. Re-addition indicates
        a regression of the dead-import review.
        """
        repo = Path(__file__).resolve().parent.parent.parent
        src = (repo / "agent" / "claude_code_sandbox.py").read_text()
        self.assertNotIn(
            "from typing import Iterable", src,
            "Iterable import was removed in B2 (b5a4dd6c1); "
            "re-add only if a SandboxComponents field actually uses it",
        )

    def test_no_init_channel_branch_in_client(self):
        """B3: the `elif channel == "init":` branch was removed from
        _apply_acp_arg_directives because no directive targeted the
        init channel. Re-addition indicates a regression.
        """
        repo = Path(__file__).resolve().parent.parent.parent
        src = (repo / "agent" / "claude_code_acp_client.py").read_text()
        self.assertNotIn(
            'channel == "init"', src,
            'init channel branch was removed in B3 (b5a4dd6c1); '
            're-add only with explicit caller that routes to init channel',
        )


if __name__ == "__main__":
    unittest.main()
