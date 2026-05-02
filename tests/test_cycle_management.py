import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.cycle_management import CycleManagement, StartCycleModal

@pytest.fixture
def mock_bot():
    return MagicMock()

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_cycle_metadata.return_value = {"state": "planning", "number": 12}
    return db

@pytest.fixture
def mock_interaction():
    interaction = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    
    # Mock channel
    channel = AsyncMock()
    channel.__class__ = discord.TextChannel
    interaction.channel = channel
    
    # Mock user
    user = MagicMock()
    user.name = "TestAdmin"
    user.id = 12345
    interaction.user = user
    
    return interaction

@pytest.mark.asyncio
async def test_start_cycle_invalid_state(mock_bot, mock_db, mock_interaction):
    """Test that start_cycle rejects when state is not 'planning'."""
    mock_db.get_cycle_metadata.return_value = {"state": "voting", "number": 12}
    
    with patch('cogs.cycle_management.MCPFirestore', return_value=mock_db):
        cog = CycleManagement(mock_bot)
        
        # Access the underlying callback function
        choice = discord.app_commands.Choice(name="Standard", value="standard")
        await cog.start_cycle.callback(cog, mock_interaction, cycle_type=choice)
        
        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        assert "Invalid state" in args[0]
        assert kwargs.get("ephemeral") is True
        mock_interaction.response.send_modal.assert_not_called()

@pytest.mark.asyncio
async def test_start_cycle_invalid_channel(mock_bot, mock_db, mock_interaction):
    """Test that start_cycle rejects when run in an invalid channel."""
    # Set channel to something other than TextChannel or ForumChannel
    mock_interaction.channel = MagicMock() # Not a TextChannel
    
    with patch('cogs.cycle_management.MCPFirestore', return_value=mock_db):
        cog = CycleManagement(mock_bot)
        
        choice = discord.app_commands.Choice(name="Standard", value="standard")
        await cog.start_cycle.callback(cog, mock_interaction, cycle_type=choice)
        
        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        assert "Invalid channel" in args[0]
        mock_interaction.response.send_modal.assert_not_called()

@pytest.mark.asyncio
async def test_start_cycle_success(mock_bot, mock_db, mock_interaction):
    """Test that start_cycle successfully opens the modal when conditions are met."""
    with patch('cogs.cycle_management.MCPFirestore', return_value=mock_db):
        cog = CycleManagement(mock_bot)
        
        choice = discord.app_commands.Choice(name="Standard", value="standard")
        await cog.start_cycle.callback(cog, mock_interaction, cycle_type=choice)
        
        mock_interaction.response.send_message.assert_not_called()
        mock_interaction.response.send_modal.assert_called_once()
        
        # Verify the modal is the correct type
        args, kwargs = mock_interaction.response.send_modal.call_args
        modal = args[0]
        assert isinstance(modal, StartCycleModal)
        assert modal.default_cycle_num == 12
        assert modal.cycle_type == "standard"
