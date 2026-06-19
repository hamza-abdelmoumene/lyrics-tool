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
    banner_hold: float = 1.5,
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
        display_now_playing_glitch, display_ad, display_searching, display_no_lyrics,
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

    # How long the *settled* now-playing card stays up before lyrics take over.
    # Timed from after the glitch resolves (see below), so the clean title is
    # always visible for this long regardless of how slow the cover/lyric
    # lookups are — that's what stops the card from flashing past. Floored so a
    # tiny value still shows a readable title.
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
        color_holder = None   # off-thread cover-colour result for the current track
        fetch_holder = None   # off-thread on-the-fly lyric fetch for the current track
        steady_until = 0.0    # monotonic instant the settled title card may hand off
        idle_phase = 0        # animation tick for the waiting / ad / searching screens

        def _notes_now():
            """Current ambient-note positions for an idle screen, or None."""
            if note_field is None:
                return None
            cols, rows = get_terminal_size()
            return note_field.positions(cols, rows, time.monotonic())

        def _pick_lyric_color():
            """Adopt the cover accent the instant the off-thread fetch lands."""
            nonlocal lyric_color
            if lyric_color is None and color_holder is not None and color_holder['done']:
                if color_holder['lyric'] is not None:
                    lyric_color = color_holder['lyric']

        def _start_bg_fetch(artist, title):
            """Kick the on-the-fly lyric fetch onto a daemon thread.

            The network round-trip (LRCLIB + fallbacks) can take several seconds;
            running it inline froze the display and swallowed track switches, so
            it runs off-thread and the loop polls ``holder['done']`` instead.
            """
            holder = {'title': title, 'done': False, 'lrc': None}

            def work():
                try:
                    holder['lrc'] = fetch_lyrics_on_the_fly(
                        artist, title, lrc_dir, is_wlrc=is_wlrc)
                except Exception:
                    holder['lrc'] = None
                finally:
                    holder['done'] = True

            threading.Thread(target=work, daemon=True).start()
            return holder

        def _load_lines(artist, title, fetched=None):
            """Resolve playable (timestamp, text) lines for the track, or None.

            Fast and filesystem-only: a local lookup (with the in-memory
            phrase→word fallback for word mode), or a path already produced by
            the background fetch. Never touches the network itself.
            """
            audio_file = get_audio_file_info()
            lookup = audio_file if audio_file else Path(title)
            lrc = fetched or find_lrc_for_audio(
                lookup, lrc_dir, artist, title, is_wlrc=is_wlrc)

            # WLRC fallback: derive word timing in-memory from a phrase-level .lrc
            # so word mode works offline for any cached song.
            if not lrc and is_wlrc and not fetched:
                phrase_lrc = find_lrc_for_audio(
                    lookup, lrc_dir, artist, title, is_wlrc=False)
                if phrase_lrc:
                    from .parser import parse_lrc
                    from .processor_main import phrases_to_words
                    words = phrases_to_words(parse_lrc(phrase_lrc))
                    return [(w['timestamp'], w['text']) for w in words] or None

            if not lrc:
                return None
            return parse_lrc_simple(lrc) or None

        def _track_changed(title):
            """True once the live player has moved off ``title`` (or to an ad)."""
            snap = sync_data.latest
            if snap is None:
                return False
            return is_ad(snap) or bool(snap.title and snap.title != title)

        def _hold_banner(title):
            """Keep the settled title card up for its full window.

            Returns False if the user skips to another track mid-hold (so the
            outer loop re-announces), True once the hold elapses. Recolours the
            card via the lyric accent if the cover lands while it's up.
            """
            while time.monotonic() < steady_until and sync_data.running:
                if _track_changed(title):
                    return False
                _pick_lyric_color()
                time.sleep(0.05)
            return True

        def _searching(title):
            """Wait (responsively) for the background fetch.

            Holds the title card until ``steady_until``, then animates a spinner.
            Returns 'fetched' when the fetch lands, 'changed' on a track switch,
            or 'stop' when shutting down — so the loop never blocks on the
            network or freezes on the card.
            """
            nonlocal idle_phase
            while sync_data.running:
                if _track_changed(title):
                    return 'changed'
                if fetch_holder is not None and fetch_holder['done']:
                    return 'fetched'
                _pick_lyric_color()
                if time.monotonic() >= steady_until:  # card hold done → animate
                    display_searching(title, _notes_now(), lyric_color, idle_phase)
                    idle_phase += 1
                time.sleep(0.1)
            return 'stop'

        def _idle_no_lyrics(title):
            """Drift the 'no synced lyrics' screen until the track changes.

            Replaces freezing on the title card forever when a song has no
            lyrics — the loop stays alive and re-announces the next track.
            """
            nonlocal idle_phase
            while sync_data.running:
                if _track_changed(title):
                    return
                _pick_lyric_color()
                display_no_lyrics(title, _notes_now(), lyric_color)
                idle_phase += 1
                time.sleep(0.12)

        while sync_data.running:
            state = get_state()
            if state is None:
                # No active player — gently animate a waiting screen.
                display_waiting(_notes_now(), idle_phase)
                idle_phase += 1
                last_title = None
                sync_data.current_title = None
                lyric_color = None
                fetch_holder = None
                time.sleep(0.2)
                continue

            # Spotify ad break → animated bored screen, no lyric lookup. Reset the
            # title so the real track re-announces with its glitch when it ends.
            if is_ad(state):
                display_ad(font_data, idle_phase, _notes_now())
                idle_phase += 1
                last_title = None
                sync_data.current_title = None
                lyric_color = None
                fetch_holder = None
                time.sleep(0.2)
                continue

            artist, title = state.artist, state.title

            # New track → announce it with a glitch burst. The album-cover colour
            # resolves off-thread (the download never blocks the announce); the
            # card reveals in whatever colour has landed, and a soft accent of it
            # tints the lyrics. ``steady_until`` is set *after* the glitch settles,
            # so the clean card is guaranteed visible for the full hold no matter
            # how slow the cover/lyric lookups are.
            if title != last_title:
                last_title = title
                sync_data.current_title = None
                fetch_holder = None
                color_holder = _resolve_colors()[0] if cover_color else None
                lyric_color = color_holder['lyric'] if color_holder else None
                display_now_playing_glitch(artist, title, font_data)
                display_now_playing(
                    artist, title, font_data,
                    bg=color_holder['card_bg'] if color_holder else None,
                    fg=color_holder['card_fg'] if color_holder else None,
                )
                steady_until = time.monotonic() + BANNER_HOLD

            # Resolve lyrics. Local/derived first (instant); only the network
            # round-trip runs off-thread so the loop never blocks on it.
            lines = _load_lines(artist, title)
            if lines is None:
                if fetch_holder is None or fetch_holder['title'] != title:
                    fetch_holder = _start_bg_fetch(artist, title)
                outcome = _searching(title)
                if outcome != 'fetched':
                    continue  # track changed or shutting down → re-loop
                lines = _load_lines(artist, title, fetched=fetch_holder['lrc'])

            if lines is None:
                # Fetch finished but found nothing → hold the card, then idle
                # gracefully instead of freezing on the title forever.
                if not _hold_banner(title):
                    continue
                _idle_no_lyrics(title)
                continue

            # Hold the settled card for its full window (skip if the user moves on).
            if not _hold_banner(title):
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
