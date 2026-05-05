import pytest
from unittest.mock import AsyncMock, MagicMock, patch

MY_USER_ID = 319946231  # whitelisted (Rita)
PARTNER_USER_ID = 8454213226  # Callum


@pytest.fixture
def update():
    u = MagicMock()
    u.effective_user.id = MY_USER_ID
    u.message.reply_text = AsyncMock()
    return u


@pytest.fixture
def context():
    c = MagicMock()
    c.user_data = {}
    return c


@pytest.fixture
def mock_cursor():
    with patch("bot.cursor") as cur, patch("bot.conn"):
        cur.fetchall.return_value = []
        cur.fetchone.return_value = None
        yield cur


async def test_add_task_happy_path(update, context, mock_cursor):
    from bot import handle_message

    async def send(text):
        update.message.text = text
        await handle_message(update, context)
        return update.message.reply_text.call_args[0][0]

    reply = await send("Add")
    assert "task name" in reply.lower()

    reply = await send("Buy groceries")
    assert "date" in reply.lower()

    reply = await send("today")
    assert "time" in reply.lower()

    reply = await send("10:00")
    assert "who" in reply.lower()

    reply = await send("Callum")
    assert "repeat" in reply.lower()

    reply = await send("One-time")
    assert "added" in reply.lower()

    # DB INSERT was called with the right data
    insert_call = mock_cursor.execute.call_args_list[-1]
    sql, params = insert_call[0]
    assert "INSERT" in sql.upper()
    assert "Buy groceries" in params

    # Flow state was cleared after completion
    assert "flow" not in context.user_data
