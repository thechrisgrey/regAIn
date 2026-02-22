"""Unit tests for the Coaching Agent system prompt.

Verifies that get_system_prompt() correctly injects prescribed skill tags
and produces appropriate fallback text when no tags are provided.
"""

from backend.agents.coaching.prompts import get_system_prompt


class TestGetSystemPrompt:
    """Tests for get_system_prompt()."""

    def test_includes_skill_tags_when_provided(self) -> None:
        """Prescribed skill tags should appear in the prompt."""
        tags = ["Python Programming", "Data Analysis", "Project Management"]
        prompt = get_system_prompt(valid_skill_tags=tags)

        assert "Python Programming" in prompt
        assert "Data Analysis" in prompt
        assert "Project Management" in prompt
        assert "use ONLY these prescribed skill tags" in prompt

    def test_fallback_when_tags_empty(self) -> None:
        """Empty tag list should produce fallback guidance."""
        prompt = get_system_prompt(valid_skill_tags=[])

        assert "use ONLY these prescribed skill tags" not in prompt
        assert 'Never use "general"' in prompt
        assert "descriptive, specific skill names" in prompt

    def test_fallback_when_tags_none(self) -> None:
        """None should produce fallback guidance (same as empty)."""
        prompt = get_system_prompt(valid_skill_tags=None)

        assert "use ONLY these prescribed skill tags" not in prompt
        assert 'Never use "general"' in prompt

    def test_no_args_produces_fallback(self) -> None:
        """Calling with no arguments should produce fallback guidance."""
        prompt = get_system_prompt()

        assert "use ONLY these prescribed skill tags" not in prompt
        assert 'Never use "general"' in prompt

    def test_always_includes_persona(self) -> None:
        """The agent persona section should always be present."""
        prompt_with = get_system_prompt(valid_skill_tags=["Test Skill"])
        prompt_without = get_system_prompt()

        for prompt in [prompt_with, prompt_without]:
            assert "REGAIN Coaching Agent" in prompt
            assert "## Persona" in prompt
            assert "## Coaching Philosophy" in prompt
            assert "## Response Style" in prompt

    def test_always_includes_tool_guidelines(self) -> None:
        """Tool usage guidelines should always be present."""
        prompt = get_system_prompt(valid_skill_tags=["AWS"])

        assert "## Tool Usage Guidelines" in prompt
        assert "read_user_profile" in prompt
        assert "log_evidence" in prompt

    def test_skill_tagging_section_present(self) -> None:
        """A 'Skill Tagging' section should always be included."""
        prompt_with = get_system_prompt(valid_skill_tags=["Python Programming"])
        prompt_without = get_system_prompt()

        assert "## Skill Tagging" in prompt_with
        assert "## Skill Tagging" in prompt_without

    def test_tags_formatted_as_comma_list(self) -> None:
        """Multiple tags should be comma-separated in the prompt."""
        tags = ["AWS", "Docker", "Kubernetes"]
        prompt = get_system_prompt(valid_skill_tags=tags)

        assert "AWS, Docker, Kubernetes" in prompt

    def test_single_tag(self) -> None:
        """A single tag should work without commas."""
        prompt = get_system_prompt(valid_skill_tags=["Machine Learning"])

        assert "Machine Learning" in prompt
        assert "use ONLY these prescribed skill tags" in prompt
