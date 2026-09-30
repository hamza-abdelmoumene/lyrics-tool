"""Keep the suite hermetic: never spawn a real ``playerctl --follow``."""
import pytest

from lyrics_tool import visualizer_player
from lyrics_tool.players import playerctl


@pytest.fixture(autouse=True)
def _no_event_follower(monkeypatch):
    monkeypatch.setattr(playerctl, "FOLLOW_EVENTS", False)
    backend = visualizer_player._backend
    if isinstance(backend, playerctl.PlayerctlBackend):
        monkeypatch.setattr(backend, "_follow_enabled", False)
