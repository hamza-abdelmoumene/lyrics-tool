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
        time.sleep(0.12)  # snappy track-change / seek detection

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


# Built-in head-start applied to every line so lyrics land *with* the vocal
# instead of a beat behind it. Players report their MPRIS position slightly
# ahead of what you actually hear (client-side audio buffering), and there is
# always sub-frame paint latency on top; leading by this much cancels both so
# the words change exactly on the beat. Stacks with the user's ``--offset``.
LYRIC_LEAD = 0.25


def run_visualizer(
    lrc_dir: Path,
    audio_dir: Optional[Path] = None,
    is_wlrc: bool = False,
    font_data: dict = None,
    refresh_rate: float = 0.05,
    sync_offset: float = 0.0,
    cover_color: bool = True,
    notes: bool = True,
    banner_hold: float = 0.8,
):
    """Run the LRC visualizer main loop.

    On every track change the song's name is announced as a full-screen card —
    tinted with the album cover's dominant colour (white text on dark covers,
    dark text on light ones) — then its lyrics start in lock-step with the
    audio on the default terminal background, with music notes drifting behind
    them. Playback position is read once per anchor (with sub-call latency
    compensation) and extrapolated with the monotonic clock between reads, so
    lines flip on time without polling the player every frame.

    ``sync_offset`` shifts lyrics in seconds: positive shows them earlier,
    negative later. It stacks on top of the built-in :data:`LYRIC_LEAD`, so the
    default of 0 already lands the words on the beat.
    """
    from .visualizer_player import get_state, get_audio_file_info, get_art_url, is_ad
    from .visualizer_display import (
        display_lyrics, display_waiting, display_now_playing,
        display_now_playing_glitch, display_ad,
        get_terminal_size, hide_cursor, show_cursor, clear_screen,
    )
    from .parser import parse_lrc_simple
    from .audio import find_lrc_for_audio
    from .cover import cover_colors, lyric_accent, vivid, text_color
    from .effects import NoteField

    # Effective head-start: built-in buffer compensation + user offset.
    lead = LYRIC_LEAD + sync_offset

    # Background note field; recomputed at a calm cadence so the diff-renderer
    # can skip frames in between (smooth motion, negligible CPU).
    note_field = NoteField() if notes else None
    NOTE_DT = 0.12

    # Total time the now-playing card stays up (glitch burst included) before
    # lyrics take over. Kept short so the words show up quickly; they re-anchor
    # to live position when they do, so there's no late/early drift. Floored so
    # the glitch still resolves cleanly even if a tiny value is passed.
    BANNER_HOLD = max(0.45, banner_hold)

    def _resolve_colors():
        """Fetch (card_bg, card_fg, lyric_color) for the current art, off-thread.

        The image download must never block the announce, so this runs in a
        daemon thread; the holder is polled after the glitch (by when it's
        usually done, especially on the cached replay path).
        """
        holder = {'done': False, 'card_bg': None, 'card_fg': None, 'lyric': None}

        def work():
            try:
                colors = cover_colors(get_art_url())
                if colors:
                    raw_bg = colors[0]
                    holder['card_bg'] = vivid(raw_bg)
                    holder['card_fg'] = text_color(holder['card_bg'])
                    holder['lyric'] = lyric_accent(raw_bg)
            except Exception:
                pass
            finally:
                holder['done'] = True

        th = threading.Thread(target=work, daemon=True)
        th.start()
        return holder, th

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
            return state.position + lead, None
        sync_data.paused = False
        now = time.monotonic()
        return state.position + (now - state.sampled_at) + lead, now

    try:
        last_title = None
        # Album-cover accent the current track's lyrics are painted in (None =
        # default terminal colour, e.g. cover_color off or art/Pillow missing).
        lyric_color = None
        color_holder = None  # off-thread cover-colour result for the current track

        while sync_data.running:
            state = get_state()
            if state is None:
                time.sleep(0.3)
                continue

            # Spotify ad break → bored screen, no lyric lookup. Reset the title
            # so the real track re-announces with its glitch when the ad ends.
            if is_ad(state):
                display_ad(font_data)
                last_title = None
                sync_data.current_title = None
                lyric_color = None
                time.sleep(0.3)
                continue

            artist, title = state.artist, state.title

            # New track → announce it with a glitch burst before anything else.
            # The album-cover colour is resolved off-thread (download never
            # blocks the announce); the card is revealed in colour once it lands,
            # and a soft accent of it tints the lyrics.
            banner_until = 0.0
            if title != last_title:
                last_title = title
                if cover_color:
                    color_holder, _ = _resolve_colors()
                else:
                    color_holder = None
                # Time the window from here so the glitch counts toward it.
                banner_until = time.monotonic() + BANNER_HOLD
                display_now_playing_glitch(artist, title, font_data)

                # Non-blocking: reveal the card in whatever colour has resolved
                # so far (often already done after the glitch, instant on the
                # cached-cover replay path). We never wait on the download here —
                # the lyrics pick the colour up later if it lands after the card.
                lyric_color = color_holder['lyric'] if color_holder else None
                display_now_playing(
                    artist, title, font_data,
                    bg=color_holder['card_bg'] if color_holder else None,
                    fg=color_holder['card_fg'] if color_holder else None,
                )

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
            last_text = None
            last_tq = None

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

                # Recompose only when the line or the note layer actually
                # changes — the notes tick on a quantised clock so we don't
                # rebuild (or repaint) the frame every spin.
                note_positions = None
                tq = None
                if note_field is not None:
                    tq = int(time.monotonic() / NOTE_DT)
                # Pick up the cover colour the moment the off-thread fetch lands
                # (so the card could appear before the download finished without
                # the lyrics missing their tint).
                if lyric_color is None and color_holder is not None and color_holder['done']:
                    new_color = color_holder['lyric']
                    if new_color is not None:
                        lyric_color = new_color
                        last_text = None  # force a repaint in the new colour

                if text != last_text or tq != last_tq:
                    last_text, last_tq = text, tq
                    if note_field is not None:
                        cols, rows = get_terminal_size()
                        note_positions = note_field.positions(cols, rows, tq * NOTE_DT)
                    display_lyrics(text, font_data=font_data, notes=note_positions,
                                   color=lyric_color)

                # Spin slower while paused — nothing advances, so save CPU.
                time.sleep(0.3 if sync_data.paused else refresh_rate)

    except KeyboardInterrupt:
        pass
    finally:
        sync_data.running = False
        show_cursor()
        clear_screen()
