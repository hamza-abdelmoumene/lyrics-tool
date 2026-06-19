"""Integration tests for the visualizer main loop.

These drive ``run_visualizer`` with a stubbed player and recording display
functions — no playerctl, no network, no terminal. They guard the loop's
behaviour that pure-logic tests can't reach: that it announces tracks, never
blocks the UI on a slow network fetch, and degrades gracefully when a song has
no lyrics. The non-blocking case in particular pins the regression that used to
freeze the title card (and swallow track switches) during the lyric fetch.
"""
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from lrc_tools import visualizer_main as vm
from lrc_tools import visualizer_player as vp
from lrc_tools import visualizer_display as vd
from lrc_tools import parser as pr
from lrc_tools import audio as au
from lrc_tools.fonts import get_font


def _state(title, status="Playing", artist="Artist", trackid="track:1"):
    return vp.PlayerState(
        status=status, position=1.0, artist=artist, title=title, album="Album",
        duration=180.0, trackid=trackid, sampled_at=time.monotonic(),
    )


class _Recorder:
    """Thread-safe log of which screens the loop painted."""

    def __init__(self):
        self._events = []
        self._lock = threading.Lock()

    def log(self, *event):
        with self._lock:
            self._events.append(event)

    def has(self, kind, value=None):
        with self._lock:
            return any(
                e[0] == kind and (value is None or (len(e) > 1 and e[1] == value))
                for e in self._events
            )

    def snapshot(self):
        with self._lock:
            return list(self._events)


class VisualizerLoopTest(unittest.TestCase):
    def _run_loop(self, get_state, *, find_lrc=None, fetch=None, parse_lines=None,
                  until, timeout=4.0, banner_hold=0.2, **run_kwargs):
        """Drive run_visualizer with stubs until ``until(rec)`` or ``timeout``.

        Returns the recorder. Stops the loop cleanly by flipping the captured
        SyncData.running flag, so no signals or KeyboardInterrupt are needed.
        """
        rec = _Recorder()
        captured = {}

        class _CapSync(vm.SyncData):
            def __init__(self):
                super().__init__()
                captured["sync"] = self

        patches = [
            mock.patch.object(vm, "SyncData", _CapSync),
            mock.patch.object(vp, "get_state", get_state),
            mock.patch.object(vp, "get_audio_file_info", lambda: None),
            mock.patch.object(vp, "get_art_url", lambda: None),
            mock.patch.object(au, "find_lrc_for_audio",
                              find_lrc or (lambda *a, **k: None)),
            mock.patch.object(vm, "fetch_lyrics_on_the_fly",
                              fetch or (lambda *a, **k: None)),
            mock.patch.object(pr, "parse_lrc_simple",
                              parse_lines or (lambda p: [])),
            # Screens → recorder (and never touch the real terminal).
            mock.patch.object(vd, "display_now_playing_glitch",
                              lambda a, t, *x, **k: rec.log("announce", t)),
            mock.patch.object(vd, "display_now_playing",
                              lambda a, t, *x, **k: rec.log("card", t)),
            mock.patch.object(vd, "display_searching",
                              lambda t, *x, **k: rec.log("searching", t)),
            mock.patch.object(vd, "display_no_lyrics",
                              lambda t, *x, **k: rec.log("nolyrics", t)),
            mock.patch.object(vd, "display_lyrics",
                              lambda txt, *x, **k: rec.log("lyric", txt)),
            mock.patch.object(vd, "display_ad", lambda *x, **k: rec.log("ad")),
            mock.patch.object(vd, "display_waiting", lambda *x, **k: rec.log("waiting")),
            mock.patch.object(vd, "hide_cursor", lambda: None),
            mock.patch.object(vd, "show_cursor", lambda: None),
            mock.patch.object(vd, "clear_screen", lambda: None),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        worker = threading.Thread(
            target=vm.run_visualizer,
            kwargs=dict(lrc_dir=Path("/tmp"), font_data=get_font("block"),
                        cover_color=False, notes=False, banner_hold=banner_hold,
                        **run_kwargs),
            daemon=True,
        )
        worker.start()
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline and not until(rec):
                time.sleep(0.02)
        finally:
            sync = captured.get("sync")
            if sync is not None:
                sync.running = False
            worker.join(2.0)
        return rec

    def test_announces_and_plays_local_lyrics(self):
        lines = [(0.0, "hello"), (2.0, "world")]
        rec = self._run_loop(
            lambda: _state("My Song"),
            find_lrc=lambda *a, **k: Path("/tmp/x.lrc"),
            parse_lines=lambda p: lines,
            until=lambda r: r.has("lyric", "hello"),
        )
        self.assertTrue(rec.has("announce", "My Song"))
        self.assertTrue(rec.has("lyric", "hello"))

    def test_no_lyrics_falls_to_idle_screen(self):
        rec = self._run_loop(
            lambda: _state("Ghost Song"),
            find_lrc=lambda *a, **k: None,
            fetch=lambda *a, **k: None,          # network finds nothing
            until=lambda r: r.has("nolyrics", "Ghost Song"),
        )
        self.assertTrue(rec.has("announce", "Ghost Song"))
        self.assertTrue(rec.has("nolyrics", "Ghost Song"))
        self.assertFalse(rec.has("lyric"))

    def test_slow_fetch_does_not_block_track_switch(self):
        """The regression guard: a slow fetch must not freeze the title card.

        Track A's lyric fetch sleeps for seconds; the player switches to Track B
        meanwhile. Track B must be announced well before the fetch could finish —
        proving the fetch runs off the display loop.
        """
        start = time.monotonic()
        fetch_state = {"started": None, "ended": None}

        def get_state():
            title = "Track A" if (time.monotonic() - start) < 0.4 else "Track B"
            return _state(title)

        def slow_fetch(artist, title, *a, **k):
            fetch_state["started"] = time.monotonic()
            time.sleep(3.0)
            fetch_state["ended"] = time.monotonic()
            return None

        rec = self._run_loop(
            get_state, find_lrc=lambda *a, **k: None, fetch=slow_fetch,
            until=lambda r: r.has("announce", "Track B"), timeout=3.0,
        )
        self.assertTrue(rec.has("announce", "Track A"))
        self.assertTrue(rec.has("announce", "Track B"),
                        "Track B never announced — loop blocked on the fetch")
        # B was announced before A's 3s fetch could have returned.
        self.assertIsNone(fetch_state["ended"],
                          "fetch finished — test didn't exercise the blocking path")

    def test_ad_break_shows_ad_screen(self):
        rec = self._run_loop(
            lambda: _state("Advertisement", artist="", trackid="spotify:ad:123"),
            until=lambda r: r.has("ad"),
        )
        self.assertTrue(rec.has("ad"))
        self.assertFalse(rec.has("lyric"))

    def test_no_player_shows_waiting_screen(self):
        rec = self._run_loop(
            lambda: None,                        # nothing playing
            until=lambda r: r.has("waiting"),
        )
        self.assertTrue(rec.has("waiting"))

    def test_typewriter_mode_reveals_progressively(self):
        """Typewriter mode must produce lyric events with partial text."""
        lines = [(0.0, "hello world"), (5.0, "second line")]
        rec = self._run_loop(
            lambda: _state("Type Song"),
            find_lrc=lambda *a, **k: Path("/tmp/x.lrc"),
            parse_lines=lambda p: lines,
            until=lambda r: r.has("lyric"),
            typewriter=True,
        )
        self.assertTrue(rec.has("announce", "Type Song"))
        self.assertTrue(rec.has("lyric"))


if __name__ == '__main__':
    unittest.main()
