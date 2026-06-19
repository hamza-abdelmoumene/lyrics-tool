"""
LRC Visualizer - Main display loop
Synchronizes lyrics with media player
"""
import time
import threading
from pathlib import Path
from typing import Optional


class SyncData:
    """Shared synchronization data for visualizer"""

    def __init__(self):
        self.latest = None  # most recent PlayerState from the monitor thread
        self.should_resync: bool = False
        self.running: bool = True
        self.current_title: Optional[str] = None
        self.paused: bool = False


def position_monitor(sync_data: SyncData, get_state_func):
    """Background thread that flags when the display loop must re-anchor.

    One playerctl call per tick detects three events — track change, pause/
    unpause and seek — and raises ``should_resync``. The latest snapshot is
    stashed in ``sync_data.latest`` so the display loop can re-anchor from it
    without spawning another subprocess.
    """
    expected_pos = None
    last_sample = None

    while sync_data.running:
        time.sleep(0.2)

        state = get_state_func()
        if state is None:
            continue
        sync_data.latest = state

        # Track change → display loop reloads lyrics and re-announces.
        if sync_data.current_title and state.title != sync_data.current_title:
            sync_data.should_resync = True
            expected_pos = None
            last_sample = None
            continue

        if state.status == 'Paused':
            if not sync_data.paused:
                sync_data.paused = True
                sync_data.should_resync = True
            expected_pos = None
            last_sample = None
            continue

        if sync_data.paused:  # just resumed
            sync_data.paused = False
            sync_data.should_resync = True

        # Seek detection: compare the reported position against where
        # free-running playback should be since the previous sample.
        if expected_pos is not None and last_sample is not None:
            expected = expected_pos + (state.sampled_at - last_sample)
            if abs(state.position - expected) > 0.5:
                sync_data.should_resync = True

        expected_pos = state.position
        last_sample = state.sampled_at


def _index_for(lines, pos: float) -> int:
    """Index of the last lyric line whose timestamp is <= pos.

    Returns -1 when ``pos`` precedes the first line (song intro), so the loop
    can show a blank screen instead of flashing the first line early.
    """
    idx = -1
    for i, (start, _) in enumerate(lines):
        if pos >= start:
            idx = i
        else:
            break
    return idx


# Tracks we've already failed to find lyrics for — don't re-hit the network
# every display tick for a song that simply has no lyrics available.
_no_lyrics_cache = set()


def fetch_lyrics_on_the_fly(artist: str, title: str, lrc_dir: Path, is_wlrc: bool = False) -> Optional[Path]:
    """Fetch lyrics for the playing track and save/process them in lrc_dir.

    Fast path: a single exact LRCLIB ``/api/get`` using the album + duration the
    player already exposes for the current track. Broader search runs only on a
    miss; repeated misses for the same track are cached to skip the network.
    """
    from .puller import (
        search_lrclib, search_syncedlyrics, _clean_title, _pick_lyrics, get_lrclib,
    )
    from .parser import parse_lrc, write_lrc
    from .processor_main import process_long_phrases, phrases_to_words
    from .visualizer_player import get_track_full

    cache_key = (artist.lower(), title.lower())
    if cache_key in _no_lyrics_cache:
        return None

    # 1. Clean the title and artist for searching
    clean_art = artist.split(', ')[0].strip() if ', ' in artist else artist
    clean_tit = _clean_title(title)

    # Pull album + duration straight from the player for an exact match.
    album = duration = None
    full = get_track_full()
    if full:
        _, _, album, duration = full

    content = None

    # Fast path: exact LRCLIB lookup (one request). The player's RAW metadata is
    # the same signature LRCLIB indexes (both originate from Spotify/Musixmatch),
    # so it's the most likely hit — try it first, clean only as a backup.
    content = get_lrclib(artist, title, album, duration)
    if not content and (clean_tit != title or clean_art != artist):
        content = get_lrclib(clean_art, clean_tit, album, duration)

    # Fallback: duration-scoped fuzzy search on clean metadata.
    if not content:
        try:
            results = search_lrclib(clean_art, clean_tit, duration)
            if results:
                content = _pick_lyrics(results[0], prefer_synced=True)
        except Exception:
            pass

    # Try the original (uncleaned) title.
    if not content and clean_tit != title:
        try:
            results = search_lrclib(clean_art, title, duration)
            if results:
                content = _pick_lyrics(results[0], prefer_synced=True)
        except Exception:
            pass

    # Last resort: syncedlyrics (multi-provider, slower).
    if not content:
        try:
            content = search_syncedlyrics(clean_art, clean_tit)
        except Exception:
            pass

    if not content:
        _no_lyrics_cache.add(cache_key)
        return None

    # Clean filename to avoid invalid characters
    def clean_filename(name):
        return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()

    safe_artist = clean_filename(artist)
    safe_title = clean_filename(title)
    
    raw_filename = f"{safe_artist} - {safe_title}.lrc"
    processed_filename = f"{safe_artist} - {safe_title}.wlrc" if is_wlrc else f"{safe_artist} - {safe_title}.lrc"
    
    processed_path = lrc_dir / processed_filename

    # Ensure directories exist
    lrc_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = lrc_dir.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / raw_filename

    try:
        # Save raw lyrics
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Parse the raw lyrics
        lines = parse_lrc(raw_path)
        if not lines:
            return None

        # Process the lines (split long phrases)
        last_ts = lines[-1]['timestamp'] if lines else 0
        estimated_duration = last_ts + 10.0
        
        processed_lines = process_long_phrases(
            lines,
            total_duration=estimated_duration,
            max_phrase_duration=2.5,
            min_phrase_duration=0.3,
            max_words_per_phrase=8
        )

        # If word-level is requested, convert phrases to words
        if is_wlrc:
            processed_lines = phrases_to_words(processed_lines)

        # Write the processed lyrics file
        write_lrc(processed_path, processed_lines)
        return processed_path
    except Exception:
        return None


def run_visualizer(
    lrc_dir: Path,
    audio_dir: Optional[Path] = None,
    is_wlrc: bool = False,
    font_data: dict = None,
    refresh_rate: float = 0.05,
    sync_offset: float = 0.0,
):
    """Run the LRC visualizer main loop.

    On every track change the song's name is announced as a full-screen card,
    then its lyrics start in lock-step with the audio. Playback position is read
    once per anchor (with sub-call latency compensation) and extrapolated with
    the monotonic clock between reads, so lines flip on time without polling the
    player every frame.

    ``sync_offset`` shifts lyrics in seconds: positive shows them earlier,
    negative later. The default of 0 should already line up with the audio.
    """
    from .visualizer_player import get_state, get_audio_file_info
    from .visualizer_display import (
        display_text, display_waiting, display_now_playing,
        hide_cursor, show_cursor, clear_screen,
    )
    from .parser import parse_lrc_simple
    from .audio import find_lrc_for_audio

    # Minimum time the now-playing card stays up so the name is readable.
    BANNER_HOLD = 1.5

    hide_cursor()
    clear_screen()
    display_waiting()

    sync_data = SyncData()

    monitor_thread = threading.Thread(
        target=position_monitor,
        args=(sync_data, get_state),
        daemon=True,
    )
    monitor_thread.start()

    def _anchor(state):
        """Return (start_pos, start_time) for the given snapshot.

        start_time is None while paused (frozen); otherwise it is the monotonic
        instant that start_pos corresponds to, latency-compensated to *now*.
        """
        if state.status == 'Paused':
            sync_data.paused = True
            return state.position + sync_offset, None
        sync_data.paused = False
        now = time.monotonic()
        return state.position + (now - state.sampled_at) + sync_offset, now

    try:
        last_title = None

        while sync_data.running:
            state = get_state()
            if state is None:
                time.sleep(0.5)
                continue

            artist, title = state.artist, state.title

            # New track → announce it before anything else.
            banner_until = 0.0
            if title != last_title:
                last_title = title
                display_now_playing(artist, title, font_data)
                banner_until = time.monotonic() + BANNER_HOLD

            audio_file = get_audio_file_info()
            lookup = audio_file if audio_file else Path(title)
            lrc = find_lrc_for_audio(lookup, lrc_dir, artist, title, is_wlrc=is_wlrc)

            # WLRC fallback: if no word-level file exists, derive word timing
            # in-memory from an existing phrase-level .lrc. Avoids a network
            # round-trip and makes word mode work offline for any cached song.
            derive_words = False
            if not lrc and is_wlrc:
                phrase_lrc = find_lrc_for_audio(lookup, lrc_dir, artist, title, is_wlrc=False)
                if phrase_lrc:
                    lrc = phrase_lrc
                    derive_words = True

            if not lrc:
                # Last resort: fetch on-the-fly
                lrc = fetch_lyrics_on_the_fly(artist, title, lrc_dir, is_wlrc=is_wlrc)

            if not lrc:
                # No lyrics — leave the now-playing card up and retry shortly.
                time.sleep(1)
                continue

            if derive_words:
                from .parser import parse_lrc
                from .processor_main import phrases_to_words
                words = phrases_to_words(parse_lrc(lrc))
                lines = [(w['timestamp'], w['text']) for w in words]
            else:
                lines = parse_lrc_simple(lrc)
            if not lines:
                time.sleep(1)
                continue

            # Hold the card for the rest of BANNER_HOLD, but bail early if the
            # user skips again (monitor keeps sync_data.latest fresh).
            skipped = False
            while time.monotonic() < banner_until and sync_data.running:
                time.sleep(0.1)
                snap = sync_data.latest
                if snap is not None and snap.title != title:
                    skipped = True
                    break
            if skipped:
                continue

            # Anchor to a fresh, precise sample for the first painted line.
            state = get_state()
            if state is None or state.title != title:
                continue
            sync_data.current_title = title
            start_pos, start_time = _anchor(state)
            idx = _index_for(lines, start_pos)
            sync_data.should_resync = False

            while sync_data.running:
                if sync_data.should_resync:
                    sync_data.should_resync = False
                    snap = sync_data.latest
                    if snap is not None and snap.title != title:
                        break  # new song → outer loop reloads + re-announces
                    if snap is not None:
                        start_pos, start_time = _anchor(snap)
                        idx = _index_for(lines, start_pos)

                if start_time is None:  # paused/frozen
                    current_pos = start_pos
                else:
                    current_pos = start_pos + (time.monotonic() - start_time)

                # Advance to the line that should be on screen now.
                while idx + 1 < len(lines) and current_pos >= lines[idx + 1][0]:
                    idx += 1

                text = '' if idx < 0 else lines[idx][1]
                # Diffed render: repaints only when the line (or terminal size)
                # changes, so this is cheap to call every tick.
                display_text(text, use_block_letters=True, font_data=font_data, clear=False)

                # Spin slower while paused — nothing advances, so save CPU.
                time.sleep(0.3 if sync_data.paused else refresh_rate)

    except KeyboardInterrupt:
        pass
    finally:
        sync_data.running = False
        show_cursor()
        clear_screen()
