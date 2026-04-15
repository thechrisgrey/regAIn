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

    def test_includes_session_opening_section(self) -> None:
        """The prompt should include a Session Opening section."""
        prompt = get_system_prompt()

        assert "## Session Opening" in prompt

    def test_session_opening_references_greeting_request(self) -> None:
        """Session Opening should reference the [greeting_request] trigger."""
        prompt = get_system_prompt()

        assert "[greeting_request]" in prompt

    def test_session_opening_lists_required_tools(self) -> None:
        """Session Opening should instruct calling required tools."""
        prompt = get_system_prompt()

        # Extract just the Session Opening section.
        start = prompt.index("## Session Opening")
        end = prompt.index("## Behavioral Rules")
        section = prompt[start:end]

        assert "read_user_profile" in section
        assert "recall_memory" in section
        assert "get_current_mission" in section
        assert "get_campaign_status" in section

    def test_session_opening_before_behavioral_rules(self) -> None:
        """Session Opening section must appear before Behavioral Rules."""
        prompt = get_system_prompt()

        opening_idx = prompt.index("## Session Opening")
        rules_idx = prompt.index("## Behavioral Rules")

        assert opening_idx < rules_idx


class TestOnetSection:
    """Tests for the O*NET career data section of the system prompt."""

    def test_prompt_mentions_onet_tools(self) -> None:
        """Prompt lists both O*NET tool names."""
        prompt = get_system_prompt(target_role="Software Engineer")
        assert "onet_search_careers" in prompt
        assert "onet_career_detail" in prompt

    def test_prompt_includes_explicit_target_role(self) -> None:
        """When target_role is provided, it appears in the prompt verbatim."""
        prompt = get_system_prompt(target_role="Registered Nurse")
        assert "Registered Nurse" in prompt

    def test_prompt_falls_back_when_target_role_missing(self) -> None:
        """When target_role is None, the prompt renders a sentinel string."""
        prompt = get_system_prompt(target_role=None)
        assert "(not yet set)" in prompt

    def test_existing_skill_tags_still_work_with_target_role(self) -> None:
        """target_role is orthogonal to skill tags — both can coexist."""
        prompt = get_system_prompt(
            valid_skill_tags=["Python Programming"],
            target_role="Data Analyst",
        )
        assert "Python Programming" in prompt
        assert "Data Analyst" in prompt
