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
        self.position: Optional[float] = None
        self.should_resync: bool = False
        self.running: bool = True
        self.current_title: Optional[str] = None
        self.paused: bool = False


def position_monitor(sync_data: SyncData, get_position_func, get_track_func, get_status_func):
    """Background thread to monitor playback position and detect seeking."""
    last_check = time.time()
    expected_pos = None

    while sync_data.running:
        time.sleep(0.2)

        track_info = get_track_func()
        if track_info and sync_data.current_title:
            if track_info[1] != sync_data.current_title:
                sync_data.should_resync = True
                continue

        if sync_data.position is None:
            continue

        actual_pos = get_position_func()
        if actual_pos is None:
            continue

        status = get_status_func()
        if status == 'Paused':
            sync_data.position = actual_pos
            sync_data.should_resync = True
            sync_data.paused = True
            expected_pos = None
            continue

        sync_data.paused = False

        if expected_pos is None:
            expected_pos = actual_pos
        else:
            elapsed = time.time() - last_check
            expected_pos += elapsed

        if abs(actual_pos - expected_pos) > 1.0:
            sync_data.position = actual_pos
            sync_data.should_resync = True

        expected_pos = actual_pos
        last_check = time.time()


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
    refresh_rate: float = 0.05
):
    """Run the LRC visualizer main loop."""
    from .visualizer_player import get_position, get_track, get_status, get_audio_file_info
    from .visualizer_display import display_text, display_waiting, hide_cursor, show_cursor, clear_screen
    from .parser import parse_lrc_simple
    from .audio import find_lrc_for_audio

    hide_cursor()
    clear_screen()
    display_waiting()

    sync_data = SyncData()

    monitor_thread = threading.Thread(
        target=position_monitor,
        args=(sync_data, get_position, get_track, get_status),
        daemon=True
    )
    monitor_thread.start()

    try:
        last_title = None

        while sync_data.running:
            track = get_track()
            if not track:
                time.sleep(1)
                continue

            artist, title = track
            song_changed = last_title and title != last_title
            last_title = title

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
                time.sleep(1)
                continue

            sync_data.current_title = title
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

            pos = get_position()
            if pos is None:
                time.sleep(1)
                continue

            if song_changed and pos > 5.0:
                for _ in range(20):
                    pos = get_position()
                    if pos is not None and pos < 5.0:
                        break
                    time.sleep(0.1)

                pos = get_position()
                if pos is None:
                    time.sleep(1)
                    continue

            idx = 0
            for i, (start, _) in enumerate(lines):
                if pos < start:
                    break
                idx = i

            start_time = time.time()
            start_pos = pos
            sync_data.position = pos

            while idx < len(lines):
                if sync_data.should_resync:
                    new_track = get_track()
                    if not new_track or new_track[1] != title:
                        break

                    new_pos = sync_data.position
                    start_time = time.time()
                    start_pos = new_pos

                    idx = 0
                    for i, (start, _) in enumerate(lines):
                        if new_pos >= start:
                            idx = i
                        else:
                            break

                    sync_data.should_resync = False

                elapsed = time.time() - start_time
                current_pos = start_pos + elapsed

                _, text = lines[idx]
                # Diffed render: repaints only when the line (or terminal size)
                # changes, so this is cheap to call every tick.
                display_text(text, use_block_letters=True, font_data=font_data, clear=False)

                if idx + 1 < len(lines):
                    next_start, _ = lines[idx + 1]
                    if current_pos >= next_start:
                        idx += 1
                        continue

                # Spin slower while paused — nothing advances, so save CPU.
                time.sleep(0.3 if sync_data.paused else refresh_rate)

    except KeyboardInterrupt:
        pass
    finally:
        sync_data.running = False
        show_cursor()
        clear_screen()
