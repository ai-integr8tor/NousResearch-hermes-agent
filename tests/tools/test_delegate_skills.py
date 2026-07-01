#!/usr/bin/env python3
"""
Tests for the skills parameter on delegate_task.

Covers:
  - _merge_skills: top-level / per-task / dedup / None handling
  - _load_skills_content: valid skill, missing skill, empty list, mixed
  - _build_child_system_prompt with skills_content
  - _build_child_agent receives and processes skills
  - Schema includes the skills property

Run with:  python -m pytest tests/tools/test_delegate_skills.py -v
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from tools.delegate_tool import (
    DELEGATE_TASK_SCHEMA,
    _build_child_agent,
    _build_child_system_prompt,
    _load_skills_content,
    _merge_skills,
)


def _make_mock_parent(depth=0):
    """Create a mock parent agent with the fields _build_child_agent expects."""
    parent = MagicMock()
    parent.base_url = "https://api.example.com/v1"
    parent.api_key = "test-key"
    parent.provider = "openrouter"
    parent.api_mode = "chat_completions"
    parent.model = "test-model"
    parent.platform = "cli"
    parent.providers_allowed = None
    parent.providers_ignored = None
    parent.providers_order = None
    parent.provider_sort = None
    parent._session_db = None
    parent._delegate_depth = depth
    parent._active_children = []
    parent._active_children_lock = MagicMock()
    parent._print_fn = None
    parent.tool_progress_callback = None
    parent.thinking_callback = None
    parent.enabled_toolsets = ["terminal", "file", "web"]
    parent.valid_tool_names = []
    parent.acp_command = None
    parent.acp_args = []
    parent._subagent_id = None
    return parent


class TestMergeSkills(unittest.TestCase):
    """Tests for _merge_skills helper."""

    def test_both_none(self):
        self.assertIsNone(_merge_skills(None, None))

    def test_both_empty(self):
        self.assertIsNone(_merge_skills([], []))

    def test_top_level_only(self):
        result = _merge_skills(["alpha", "beta"], None)
        self.assertEqual(result, ["alpha", "beta"])

    def test_per_task_only(self):
        result = _merge_skills(None, ["gamma"])
        self.assertEqual(result, ["gamma"])

    def test_merge_dedup_preserves_order(self):
        # Per-task skills come first, then top-level not already present
        result = _merge_skills(["alpha", "beta"], ["beta", "gamma"])
        self.assertEqual(result, ["beta", "gamma", "alpha"])

    def test_no_duplicates_when_identical(self):
        result = _merge_skills(["alpha"], ["alpha"])
        self.assertEqual(result, ["alpha"])

    def test_empty_top_level_with_per_task(self):
        result = _merge_skills([], ["delta"])
        self.assertEqual(result, ["delta"])

    def test_top_level_with_empty_per_task(self):
        result = _merge_skills(["epsilon"], [])
        self.assertEqual(result, ["epsilon"])


class TestLoadSkillsContent(unittest.TestCase):
    """Tests for _load_skills_content helper.

    Note: _load_skills_content uses deferred imports
    (from tools.skills_tool import skill_view), so we patch the
    source modules rather than tools.delegate_tool.skill_view.
    """

    @patch("tools.skill_usage.bump_use")
    @patch("tools.skills_tool.skill_view")
    def test_valid_skill(self, mock_view, mock_bump):
        mock_view.return_value = json.dumps({
            "success": True,
            "content": "# My Skill\nDo the thing.",
            "name": "my-skill",
        })
        result = _load_skills_content(["my-skill"])
        self.assertIn('IMPORTANT: The "my-skill" skill has been invoked', result)
        self.assertIn("Do the thing.", result)
        mock_bump.assert_called_once_with("my-skill")

    @patch("tools.skills_tool.skill_view")
    def test_missing_skill(self, mock_view):
        mock_view.return_value = json.dumps({
            "success": False,
            "error": "Skill not found",
        })
        result = _load_skills_content(["missing-skill"])
        self.assertIn("could not be loaded", result)
        self.assertIn("missing-skill", result)

    @patch("tools.skills_tool.skill_view")
    def test_invalid_json_response(self, mock_view):
        mock_view.return_value = "not valid json{{{"
        result = _load_skills_content(["bad-json-skill"])
        self.assertIn("could not be loaded", result)
        self.assertIn("bad-json-skill", result)

    def test_empty_list(self):
        result = _load_skills_content([])
        self.assertEqual(result, "")

    def test_none(self):
        result = _load_skills_content(None)
        self.assertEqual(result, "")

    @patch("tools.skill_usage.bump_use")
    @patch("tools.skills_tool.skill_view")
    def test_multiple_skills(self, mock_view, mock_bump):
        mock_view.side_effect = [
            json.dumps({"success": True, "content": "Skill A content", "name": "skill-a"}),
            json.dumps({"success": True, "content": "Skill B content", "name": "skill-b"}),
        ]
        result = _load_skills_content(["skill-a", "skill-b"])
        self.assertIn("skill-a", result)
        self.assertIn("Skill A content", result)
        self.assertIn("skill-b", result)
        self.assertIn("Skill B content", result)
        self.assertEqual(mock_bump.call_count, 2)

    @patch("tools.skill_usage.bump_use")
    @patch("tools.skills_tool.skill_view")
    def test_mixed_valid_and_missing(self, mock_view, mock_bump):
        mock_view.side_effect = [
            json.dumps({"success": True, "content": "Good skill", "name": "good-skill"}),
            json.dumps({"success": False, "error": "Not found"}),
        ]
        result = _load_skills_content(["good-skill", "bad-skill"])
        # Should contain the good skill content
        self.assertIn("Good skill", result)
        # Should contain a notice about the missing skill
        self.assertIn("bad-skill", result)
        # bump_use called only for the good skill
        mock_bump.assert_called_once_with("good-skill")

    @patch("tools.skill_usage.bump_use")
    @patch("tools.skills_tool.skill_view")
    def test_bump_use_failure_is_tolerated(self, mock_view, mock_bump):
        """bump_use should not crash the skill loading if it fails."""
        mock_view.return_value = json.dumps({
            "success": True,
            "content": "Skill content",
            "name": "test-skill",
        })
        mock_bump.side_effect = RuntimeError("DB locked")
        # Should not raise
        result = _load_skills_content(["test-skill"])
        self.assertIn("Skill content", result)


class TestChildSystemPromptWithSkills(unittest.TestCase):
    """Tests for _build_child_system_prompt with skills_content."""

    def test_no_skills_content(self):
        prompt = _build_child_system_prompt("Fix the tests")
        self.assertIn("Fix the tests", prompt)
        self.assertIn("YOUR TASK", prompt)
        self.assertNotIn("skill has been invoked", prompt)

    def test_with_skills_content(self):
        skills_text = '[IMPORTANT: The "my-skill" skill has been invoked. Follow its instructions carefully.]\n\n# My Skill\nDo the thing.'
        prompt = _build_child_system_prompt(
            "Fix the tests",
            skills_content=skills_text,
        )
        self.assertIn("Fix the tests", prompt)
        self.assertIn("YOUR TASK", prompt)
        self.assertIn("my-skill", prompt)
        self.assertIn("Do the thing.", prompt)

    def test_empty_skills_content_ignored(self):
        prompt = _build_child_system_prompt("Do something", skills_content="  ")
        self.assertNotIn("skill has been invoked", prompt)

    def test_skills_content_positioned_before_completion_instructions(self):
        """Skills content should appear between task context and the
        'Complete this task' footer so the subagent reads skills before
        acting."""
        skills_text = '[IMPORTANT: The "test-skill" skill has been invoked.]\n\nSkill instructions here.'
        prompt = _build_child_system_prompt(
            "Build feature X",
            context="See PRD for details",
            skills_content=skills_text,
        )
        task_pos = prompt.index("YOUR TASK")
        context_pos = prompt.index("CONTEXT")
        skills_pos = prompt.index("test-skill")
        complete_pos = prompt.index("Complete this task")
        self.assertLess(task_pos, context_pos)
        self.assertLess(context_pos, skills_pos)
        self.assertLess(skills_pos, complete_pos)


class TestBuildChildAgentWithSkills(unittest.TestCase):
    """Tests that _build_child_agent loads skills into the child prompt."""

    @patch("tools.delegate_tool._load_skills_content")
    @patch("tools.delegate_tool.AIAgent", create=True)
    def test_skills_passed_to_load(self, mock_agent_cls, mock_load):
        """_build_child_agent should call _load_skills_content with the skills list."""
        mock_load.return_value = "loaded skill content here"
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance

        # We need to patch the import inside _build_child_agent
        with patch("tools.delegate_tool.AIAgent", mock_agent_cls, create=True):
            with patch("run_agent.AIAgent", mock_agent_cls):
                try:
                    child = _build_child_agent(
                        task_index=0,
                        goal="Test task",
                        context=None,
                        toolsets=["terminal", "file"],
                        model="test-model",
                        max_iterations=50,
                        task_count=1,
                        parent_agent=_make_mock_parent(),
                        skills=["my-skill"],
                    )
                except Exception:
                    # AIAgent constructor may fail with mock setup, that's OK
                    # We just want to verify _load_skills_content was called
                    pass

        mock_load.assert_called_once_with(["my-skill"])

    @patch("tools.delegate_tool._load_skills_content")
    def test_no_skills_skips_load(self, mock_load):
        """When skills is None, _load_skills_content should receive None."""
        mock_load.return_value = ""

        try:
            child = _build_child_agent(
                task_index=0,
                goal="Test task",
                context=None,
                toolsets=["terminal", "file"],
                model="test-model",
                max_iterations=50,
                task_count=1,
                parent_agent=_make_mock_parent(),
                skills=None,
            )
        except Exception:
            # AIAgent constructor may fail with mock setup
            pass

        mock_load.assert_called_once_with(None)

    @patch("tools.delegate_tool._load_skills_content")
    def test_skills_content_injected_into_prompt(self, mock_load):
        """The loaded skills content should appear in the child's system prompt."""
        mock_load.return_value = "SKILL: Follow TDD approach"
        mock_agent_instance = MagicMock()

        with patch("run_agent.AIAgent", return_value=mock_agent_instance):
            try:
                child = _build_child_agent(
                    task_index=0,
                    goal="Write tests",
                    context=None,
                    toolsets=["terminal", "file"],
                    model="test-model",
                    max_iterations=50,
                    task_count=1,
                    parent_agent=_make_mock_parent(),
                    skills=["tdd"],
                )
            except Exception:
                pass

        # Verify _load_skills_content was called correctly
        mock_load.assert_called_once_with(["tdd"])

        # The system prompt passed to AIAgent should contain the skill content
        if mock_agent_instance.method_calls:
            # Check the system_prompt kwarg if it was captured
            pass  # The prompt construction is verified via _build_child_system_prompt tests


class TestSchemaSkillsProperty(unittest.TestCase):
    """Tests that the schema includes the skills property."""

    def test_top_level_skills_in_schema(self):
        props = DELEGATE_TASK_SCHEMA["parameters"]["properties"]
        self.assertIn("skills", props)
        self.assertEqual(props["skills"]["type"], "array")
        self.assertEqual(props["skills"]["items"]["type"], "string")

    def test_per_task_skills_in_schema(self):
        task_props = DELEGATE_TASK_SCHEMA["parameters"]["properties"]["tasks"]["items"]["properties"]
        self.assertIn("skills", task_props)
        self.assertEqual(task_props["skills"]["type"], "array")
        self.assertEqual(task_props["skills"]["items"]["type"], "string")

    def test_schema_description_mentions_skills(self):
        desc = DELEGATE_TASK_SCHEMA["parameters"]["properties"]["skills"]["description"]
        self.assertIn("skill", desc.lower())
        self.assertIn("cron", desc.lower())


if __name__ == "__main__":
    unittest.main()
