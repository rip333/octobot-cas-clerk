import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.voting import Voting, VotingView

@pytest.fixture
def mock_bot():
    return MagicMock()

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

@pytest.fixture
def mock_interaction():
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Mock user
    user = MagicMock()
    user.name = "TestVoter"
    user.id = 54321
    interaction.user = user
    
    # Mock guild
    guild = MagicMock()
    guild.roles = []
    interaction.guild = guild
    
    return interaction

@pytest.mark.asyncio
async def test_vote_invalid_state(mock_bot, mock_db, mock_interaction):
    """Test that /vote rejects when state is not 'voting'."""
    mock_db.get_cycle_metadata.return_value = {"state": "nominations"}
    
    with patch('cogs.voting.MCPFirestore', return_value=mock_db):
        cog = Voting(mock_bot)
        
        await cog.vote.callback(cog, mock_interaction)
        
        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        args, kwargs = mock_interaction.followup.send.call_args
        assert "Voting is not open right now" in args[0]

@pytest.mark.asyncio
async def test_vote_success_empty_nominations(mock_bot, mock_db, mock_interaction):
    """Test that /vote handles empty nominations."""
    mock_db.get_cycle_metadata.return_value = {"state": "voting"}
    mock_db.get_nominations.return_value = []
    
    with patch('cogs.voting.MCPFirestore', return_value=mock_db):
        cog = Voting(mock_bot)
        
        await cog.vote.callback(cog, mock_interaction)
        
        mock_interaction.followup.send.assert_called_once()
        args, kwargs = mock_interaction.followup.send.call_args
        assert "no active nominations to vote on" in args[0]

@pytest.mark.asyncio
async def test_vote_success(mock_bot, mock_db, mock_interaction):
    """Test that /vote successfully sends the voting view when nominations exist."""
    mock_db.get_cycle_metadata.return_value = {"state": "voting"}
    
    # Provide fake nominations
    mock_db.get_nominations.return_value = [
        {"set_name": "Test Hero 1", "category": "Hero", "creatorName": "Creator 1"},
        {"set_name": "Test Villain 1", "category": "Encounter", "creatorName": "Creator 2"}
    ]
    
    with patch('cogs.voting.MCPFirestore', return_value=mock_db):
        cog = Voting(mock_bot)
        
        await cog.vote.callback(cog, mock_interaction)
        
        mock_interaction.followup.send.assert_called_once()
        args, kwargs = mock_interaction.followup.send.call_args
        
        # Check that the View was sent
        view = kwargs.get("view")
        assert isinstance(view, VotingView)
        assert len(view.hero_selects[0].options) == 1
        assert len(view.encounter_select.options) == 1
