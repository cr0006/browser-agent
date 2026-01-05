"""Tests for the browser agent."""

import pytest


def test_config_loads():
    """Test that configuration loads correctly."""
    from src.config import Config
    
    config = Config()
    assert config.llm_provider in ("anthropic", "openai")
    assert config.confidence_threshold > 0
    assert config.max_iterations > 0


def test_session_creation():
    """Test session creation."""
    from src.core.session import Session
    
    session = Session.create("https://example.com")
    assert session.session_id is not None
    assert session.target_url == "https://example.com"
    assert session.status == "active"


def test_action_record():
    """Test action recording."""
    from src.core.session import ActionRecord, Session
    
    session = Session.create("https://example.com")
    action = ActionRecord(
        timestamp="2024-01-01T00:00:00",
        action_type="click",
        selector="#button",
        value=None,
        reasoning="Testing",
        success=True,
        page_url="https://example.com",
    )
    session.add_action(action)
    
    assert len(session.actions) == 1
    assert session.success_rate == 1.0


def test_confidence_metrics():
    """Test confidence score calculation."""
    from src.learning.confidence_scorer import ConfidenceMetrics
    
    metrics = ConfidenceMetrics(
        coverage_score=0.8,
        success_rate=0.9,
        pattern_stability=0.7,
        exploration_depth=0.6,
    )
    
    # Weighted: 0.8*0.3 + 0.9*0.25 + 0.7*0.25 + 0.6*0.2 = 0.24 + 0.225 + 0.175 + 0.12 = 0.76
    assert 0.75 < metrics.weighted_score < 0.77


def test_action_dataclass():
    """Test Action dataclass."""
    from src.intelligence.llm_client import Action
    
    action_data = {
        "action": "click",
        "selector": "#submit",
        "value": None,
        "reasoning": "Submit the form",
        "confidence": 0.9,
    }
    
    action = Action.from_dict(action_data)
    assert action.type == "click"
    assert action.confidence == 0.9
