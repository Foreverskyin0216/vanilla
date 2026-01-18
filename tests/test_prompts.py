"""Tests for prompts module."""

from src.prompts import ADD_REACTION_INSTRUCTIONS, VANILLA_PERSONALITY


def test_vanilla_personality_exists():
    """Test VANILLA_PERSONALITY prompt exists and has content."""
    assert VANILLA_PERSONALITY is not None
    assert len(VANILLA_PERSONALITY) > 100


def test_vanilla_personality_has_placeholder():
    """Test VANILLA_PERSONALITY has bot_name placeholder."""
    assert "{bot_name}" in VANILLA_PERSONALITY


def test_vanilla_personality_format():
    """Test VANILLA_PERSONALITY can be formatted."""
    formatted = VANILLA_PERSONALITY.format(bot_name="香草")
    assert "香草" in formatted
    assert "{bot_name}" not in formatted


def test_add_reaction_instructions_exists():
    """Test ADD_REACTION_INSTRUCTIONS exists and has content."""
    assert ADD_REACTION_INSTRUCTIONS is not None
    assert len(ADD_REACTION_INSTRUCTIONS) > 100


def test_add_reaction_instructions_has_reactions():
    """Test ADD_REACTION_INSTRUCTIONS contains reaction types."""
    assert "NICE" in ADD_REACTION_INSTRUCTIONS
    assert "LOVE" in ADD_REACTION_INSTRUCTIONS
    assert "FUN" in ADD_REACTION_INSTRUCTIONS
    assert "AMAZING" in ADD_REACTION_INSTRUCTIONS
    assert "SAD" in ADD_REACTION_INSTRUCTIONS
    assert "OMG" in ADD_REACTION_INSTRUCTIONS
    assert "ALL" in ADD_REACTION_INSTRUCTIONS
