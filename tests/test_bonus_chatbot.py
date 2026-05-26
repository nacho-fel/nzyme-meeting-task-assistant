from app.services.chatbot_service import GroundedChatbotService
from app.services.data_store import DataStore
from app.core.config import get_settings


def test_grounded_chatbot_refuses_out_of_scope(monkeypatch):
    ds = DataStore(get_settings().data_dir)
    bot = GroundedChatbotService(ds)
    response = bot.answer("What is the weather in Madrid?")
    assert "only answer" in response.answer.lower()
    assert response.tasks == []


def test_grounded_chatbot_can_list_projects():
    ds = DataStore(get_settings().data_dir)
    bot = GroundedChatbotService(ds)
    response = bot.answer("List active projects")
    assert "Active projects" in response.answer
    assert "PRJ" in response.answer
