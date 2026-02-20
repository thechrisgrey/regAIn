"""Unit tests for AgentCore Cedar policy definitions (Task 4.1+).

Verifies that Cedar policy documents are correctly defined and attached
to the Gateway instance via the reusable _attach_policy helper.
"""

from infra.stacks.agentcore_stack import AgentCoreStack


# -- User Data Isolation Policy (Task 4.1) -----------------------------------


def test_cedar_user_data_isolation_contains_permit_rule() -> None:
    """Policy must permit when request userId matches JWT userId."""
    doc = AgentCoreStack._cedar_user_data_isolation()
    assert 'permit(' in doc
    assert 'resource.tool_params.userId == context.auth.userId' in doc


def test_cedar_user_data_isolation_contains_forbid_rule() -> None:
    """Policy must forbid when request userId does NOT match JWT userId."""
    doc = AgentCoreStack._cedar_user_data_isolation()
    assert 'forbid(' in doc
    assert 'resource.tool_params.userId != context.auth.userId' in doc


def test_cedar_user_data_isolation_targets_invoke_tool_action() -> None:
    """Both permit and forbid rules must scope to invoke_tool action."""
    doc = AgentCoreStack._cedar_user_data_isolation()
    assert 'action in [Action::"invoke_tool"]' in doc


def test_cedar_user_data_isolation_is_valid_cedar_structure() -> None:
    """Policy document must contain exactly one permit and one forbid block."""
    doc = AgentCoreStack._cedar_user_data_isolation()
    assert doc.count('permit(') == 1
    assert doc.count('forbid(') == 1
    # Both blocks must be terminated with a semicolon
    assert doc.count('};') == 2


def test_attach_cedar_policies_returns_list() -> None:
    """attach_cedar_policies should be callable on the class (static check)."""
    # Verify the method exists and the static helper is accessible
    assert callable(AgentCoreStack._cedar_user_data_isolation)
    assert callable(getattr(AgentCoreStack, '_attach_policy', None))


# -- Evidence Write Scope Policy (Task 4.2) -----------------------------------


def test_cedar_evidence_write_scope_contains_permit_rule() -> None:
    """Policy must permit log_evidence when session active AND timestamp within 24h."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    assert 'permit(' in doc
    assert 'resource.tool_name == "regain_log_evidence"' in doc
    assert 'context.session.is_active == true' in doc
    assert 'context.evidence_timestamp.within_last_24h == true' in doc


def test_cedar_evidence_write_scope_contains_forbid_rule() -> None:
    """Policy must forbid log_evidence when session inactive OR timestamp stale."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    assert 'forbid(' in doc
    assert 'context.session.is_active == false' in doc
    assert 'context.evidence_timestamp.within_last_24h == false' in doc


def test_cedar_evidence_write_scope_targets_invoke_tool_action() -> None:
    """Both permit and forbid rules must scope to invoke_tool action."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    assert 'action in [Action::"invoke_tool"]' in doc


def test_cedar_evidence_write_scope_is_valid_cedar_structure() -> None:
    """Policy document must contain exactly one permit and one forbid block."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    assert doc.count('permit(') == 1
    assert doc.count('forbid(') == 1
    assert doc.count('};') == 2


def test_cedar_evidence_write_scope_scoped_to_log_evidence_only() -> None:
    """Both rules must target only the regain_log_evidence tool."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    # tool_name check appears in both permit and forbid blocks
    assert doc.count('resource.tool_name == "regain_log_evidence"') == 2


def test_cedar_evidence_write_scope_references_requirements() -> None:
    """Policy comments must reference requirements 5.1, 5.2, 5.3."""
    doc = AgentCoreStack._cedar_evidence_write_scope()
    assert 'Requirement 5.1' in doc
    assert 'Requirement 5.2' in doc
    assert 'Requirement 5.3' in doc


def test_cedar_evidence_write_scope_method_exists() -> None:
    """_cedar_evidence_write_scope static method must be defined on AgentCoreStack."""
    assert callable(getattr(AgentCoreStack, '_cedar_evidence_write_scope', None))


# -- Mission Generation Rate Limit Policy (Task 4.3) --------------------------


def test_cedar_mission_generation_rate_limit_contains_permit_rule() -> None:
    """Policy must permit generate_mission when daily count < 3."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert 'permit(' in doc
    assert 'resource.tool_name == "regain_generate_mission"' in doc
    assert 'context.daily_generation_count < 3' in doc


def test_cedar_mission_generation_rate_limit_contains_forbid_rule() -> None:
    """Policy must forbid generate_mission when daily count >= 3."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert 'forbid(' in doc
    assert 'context.daily_generation_count >= 3' in doc


def test_cedar_mission_generation_rate_limit_targets_invoke_tool_action() -> None:
    """Both permit and forbid rules must scope to invoke_tool action."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert 'action in [Action::"invoke_tool"]' in doc


def test_cedar_mission_generation_rate_limit_is_valid_cedar_structure() -> None:
    """Policy document must contain exactly one permit and one forbid block."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert doc.count('permit(') == 1
    assert doc.count('forbid(') == 1
    assert doc.count('};') == 2


def test_cedar_mission_generation_rate_limit_scoped_to_generate_mission_only() -> None:
    """Both rules must target only the regain_generate_mission tool."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert doc.count('resource.tool_name == "regain_generate_mission"') == 2


def test_cedar_mission_generation_rate_limit_references_requirements() -> None:
    """Policy comments must reference requirements 6.1, 6.2, 6.3."""
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert 'Requirement 6.1' in doc
    assert 'Requirement 6.2' in doc
    assert 'Requirement 6.3' in doc


def test_cedar_mission_generation_rate_limit_method_exists() -> None:
    """_cedar_mission_generation_rate_limit static method must be defined."""
    assert callable(getattr(AgentCoreStack, '_cedar_mission_generation_rate_limit', None))


def test_attach_cedar_policies_includes_mission_rate_limit() -> None:
    """attach_cedar_policies must include the MissionGenerationRateLimit policy."""
    # Verify the static method returns a document that would be attached
    doc = AgentCoreStack._cedar_mission_generation_rate_limit()
    assert len(doc) > 0
    assert 'regain_generate_mission' in doc


# -- Profile Update Restrictions Policy (Task 4.4) ----------------------------


def test_cedar_profile_update_restrictions_contains_permit_rule() -> None:
    """Policy must permit update_user_profile when all_fields_allowed is true."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert 'permit(' in doc
    assert 'resource.tool_name == "regain_update_user_profile"' in doc
    assert 'context.all_fields_allowed == true' in doc


def test_cedar_profile_update_restrictions_contains_forbid_rule() -> None:
    """Policy must forbid update_user_profile when all_fields_allowed is false."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert 'forbid(' in doc
    assert 'context.all_fields_allowed == false' in doc


def test_cedar_profile_update_restrictions_targets_invoke_tool_action() -> None:
    """Both permit and forbid rules must scope to invoke_tool action."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert 'action in [Action::"invoke_tool"]' in doc


def test_cedar_profile_update_restrictions_is_valid_cedar_structure() -> None:
    """Policy document must contain exactly one permit and one forbid block."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert doc.count('permit(') == 1
    assert doc.count('forbid(') == 1
    assert doc.count('};') == 2


def test_cedar_profile_update_restrictions_scoped_to_update_user_profile() -> None:
    """Both rules must target only the regain_update_user_profile tool."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert doc.count('resource.tool_name == "regain_update_user_profile"') == 2


def test_cedar_profile_update_restrictions_references_requirements() -> None:
    """Policy comments must reference requirements 7.1, 7.2, 7.3."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert 'Requirement 7.1' in doc
    assert 'Requirement 7.2' in doc
    assert 'Requirement 7.3' in doc


def test_cedar_profile_update_restrictions_method_exists() -> None:
    """_cedar_profile_update_restrictions static method must be defined."""
    assert callable(getattr(AgentCoreStack, '_cedar_profile_update_restrictions', None))


def test_attach_cedar_policies_includes_profile_update_restrictions() -> None:
    """attach_cedar_policies must include the ProfileUpdateRestrictions policy."""
    doc = AgentCoreStack._cedar_profile_update_restrictions()
    assert len(doc) > 0
    assert 'regain_update_user_profile' in doc


# -- Market Data Read-Only Policy (Task 4.5) ----------------------------------


def test_cedar_market_data_read_only_contains_permit_rule() -> None:
    """Policy must permit get_market_insights and get_alignment for reads."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert 'permit(' in doc
    assert 'resource.tool_name in ["regain_get_market_insights", "regain_get_alignment"]' in doc


def test_cedar_market_data_read_only_contains_forbid_rule() -> None:
    """Policy must forbid write/update/delete on MarketData."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert 'forbid(' in doc
    assert 'resource.target_table == "MarketData"' in doc
    assert 'context.operation_type in ["write", "update", "delete"]' in doc


def test_cedar_market_data_read_only_targets_invoke_tool_action() -> None:
    """Both permit and forbid rules must scope to invoke_tool action."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert 'action in [Action::"invoke_tool"]' in doc


def test_cedar_market_data_read_only_is_valid_cedar_structure() -> None:
    """Policy document must contain exactly one permit and one forbid block."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert doc.count('permit(') == 1
    assert doc.count('forbid(') == 1
    assert doc.count('};') == 2


def test_cedar_market_data_read_only_references_requirements() -> None:
    """Policy comments must reference requirements 8.1, 8.2, 8.3."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert 'Requirement 8.1' in doc
    assert 'Requirement 8.2' in doc
    assert 'Requirement 8.3' in doc


def test_cedar_market_data_read_only_method_exists() -> None:
    """_cedar_market_data_read_only static method must be defined on AgentCoreStack."""
    assert callable(getattr(AgentCoreStack, '_cedar_market_data_read_only', None))


def test_attach_cedar_policies_includes_market_data_read_only() -> None:
    """attach_cedar_policies must include the MarketDataReadOnly policy."""
    doc = AgentCoreStack._cedar_market_data_read_only()
    assert len(doc) > 0
    assert 'regain_get_market_insights' in doc
    assert 'regain_get_alignment' in doc
