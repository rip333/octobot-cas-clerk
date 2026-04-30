import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.process_nominations import ProcessNominations

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.fetch_channel = AsyncMock()
    # bot.user is used to ignore bot messages in history
    bot.user = MagicMock()
    bot.user.id = 999
    return bot

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_cycle_metadata.return_value = {"state": "nominations", "nomination_thread_id": 1234, "number": 12}
    db.get_rules.return_value = "Test Rules"
    db.get_ineligible_creators.return_value = (["Hero1"], ["Villain1"])
    db.clear_nominations.return_value = 5
    db.add_nomination_batch = MagicMock()
    return db

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.process_thread.return_value = {
        "nominations": [
            {
                "nominator_id": "111",
                "nominator_name": "TestUser",
                "set_name": "Test Set",
                "category": "Hero",
                "creator_name": "Test Creator",
                "creator_discord_id": "222",
                "ip_category": "Marvel"
            }
        ]
    }
    return agent

@pytest.fixture
def mock_interaction():
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    user = MagicMock()
    user.name = "TestAdmin"
    interaction.user = user
    return interaction

# Async iterator helper to mock channel.history
class AsyncIter:
    def __init__(self, items):
        self.items = items

    async def __aiter__(self):
        for item in self.items:
            yield item

@pytest.mark.asyncio
async def test_tally_nominations_invalid_state(mock_bot, mock_db, mock_agent, mock_interaction):
    """Test rejection when not in nominations state."""
    mock_db.get_cycle_metadata.return_value = {"state": "planning"}
    
    with patch('cogs.process_nominations.MCPFirestore', return_value=mock_db), \
         patch('cogs.process_nominations.GeminiAgent', return_value=mock_agent):
         
        cog = ProcessNominations(mock_bot)
        await cog.tally_nominations.callback(cog, mock_interaction)
        
        mock_interaction.followup.send.assert_called_once()
        args, kwargs = mock_interaction.followup.send.call_args
        assert "Invalid state" in args[0]

@pytest.mark.asyncio
async def test_tally_nominations_success(mock_bot, mock_db, mock_agent, mock_interaction):
    """Test successful processing of thread history."""
    
    # Mock channel and its history
    mock_channel = MagicMock()
    
    mock_msg = MagicMock()
    mock_msg.author.name = "TestUser"
    mock_msg.author.id = "111"
    mock_msg.content = "I nominate Test Set by Test Creator"
    
    # Make history return our mocked messages
    mock_channel.history = MagicMock(return_value=AsyncIter([mock_msg]))
    mock_bot.fetch_channel.return_value = mock_channel
    
    with patch('cogs.process_nominations.MCPFirestore', return_value=mock_db), \
         patch('cogs.process_nominations.GeminiAgent', return_value=mock_agent):
         
        cog = ProcessNominations(mock_bot)
        await cog.tally_nominations.callback(cog, mock_interaction)
        
        # Verify db calls
        mock_db.clear_nominations.assert_called_once()
        mock_db.add_nomination_batch.assert_called_once()
        
        args, kwargs = mock_db.add_nomination_batch.call_args
        assert kwargs["cycle_number"] == 12
        assert kwargs["nominator_id"] == "111"
        assert len(kwargs["sets"]) == 1
        
        # Verify followup messages
        assert mock_interaction.followup.send.call_count >= 2
        last_call_args = mock_interaction.followup.send.call_args_list[-1][0]
        assert "Successfully processed thread" in last_call_args[0]
