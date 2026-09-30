"""
LRC Visualizer - Main display loop
Synchronizes lyrics with media player
"""
import time
import threading
from pathlib import Path
from typing import Optional

from .keyinput import KeyReader
from .sync import QuantumDetector


class SyncData:
    """Shared state between the monitor thread and the display loop.

    Deliberately lock-free: every field is a single word (a flag, a string, or
    an immutable PlayerState reference) written by one side and read by the
    other, so under CPython's GIL each access is atomic. The only contended
    flags (``should_resync``, ``paused``) are idempotent — the worst a race can
    cause is one extra, harmless re-anchor — so a mutex would add risk (a lock
    held across the render loop) for no correctness gain.
    """

    def __init__(self):
        self.latest = None  # most recent PlayerState from the monitor thread
        self.should_resync: bool = False
        self.running: bool = True
        self.current_title: Optional[str] = None
        self.paused: bool = False
        # Position granularity of the current player: 1.0 when it reports whole
        # seconds (cmus), 0.0 when precise. Learned by the monitor thread.
        self.quantum: float = 0.0


def position_monitor(sync_data: SyncData, get_state_func):
    """Background thread that flags when the display loop must re-anchor.

    One playerctl call per tick detects three events — track change, pause/
    unpause and seek — and raises ``should_resync``. The latest snapshot is
    stashed in ``sync_data.latest`` so the display loop can re-anchor from it
    without spawning another subprocess.
    """
    expected_pos = None
    last_sample = None
    quantum = QuantumDetector()

    while sync_data.running:
        time.sleep(0.12)  # snappy track-change / seek detection

        state = get_state_func()
        if state is None:
            continue
        sync_data.quantum = quantum.update(state.position)
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
        # free-running playback should be since the previous sample. A coarse
        # player's truncated position legitimately lags by up to one quantum,
        # so widen the tolerance by it or every second tick reads as a seek.
        if expected_pos is not None and last_sample is not None:
            expected = expected_pos + (state.sampled_at - last_sample)
            if abs(state.position - expected) > 0.5 + sync_data.quantum:
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


# Built-in head-start applied to every line, in seconds. Positive shows lyrics
# earlier than the raw player position; negative, later.
#
# Default 0.0 deliberately matches what the desktop media widget shows: it
# highlights the lyric for the player's *raw* MPRIS position, so a non-zero lead
# here is precisely what made the terminal lyrics run ahead of the widget. Any
# read-ahead is now a per-taste choice, dialled live with the +/- keys (which
# persist) or pinned with ``--offset`` / ``$LYRICSOOO_LYRIC_LEAD``.
def _default_lead() -> float:
    """Built-in lead, overridable via ``$LYRICSOOO_LYRIC_LEAD`` (seconds)."""
    import os
    raw = os.environ.get('LYRICSOOO_LYRIC_LEAD')
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 0.0


LYRIC_LEAD = _default_lead()

# Step (seconds) each +/- keypress slides the lyrics while playing.
NUDGE_STEP = 0.05

# How far (seconds) the playback estimate may slip back behind the current
# line's start before the display actually steps back to the previous line.
BACKSTEP_TOLERANCE = 0.4


def _load_saved_offset() -> float:
    """Read the persisted live-nudge offset (seconds), or 0.0 if unset."""
    from .paths import sync_offset_file
    try:
        return float(sync_offset_file().read_text().strip())
    except Exception:
        return 0.0


def _save_offset(value: float) -> None:
    """Persist the live-nudge offset so it survives the next launch."""
    from .paths import sync_offset_file, ensure_dir
    try:
        path = sync_offset_file()
        ensure_dir(path.parent)
        path.write_text(f'{value:.3f}\n')
    except Exception:
        pass


# Live sync-nudge keys are read through the cross-platform ``keyinput.KeyReader``
# (POSIX termios + Windows msvcrt, no-op without a TTY).


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
    color_provider=None,
    reveal: str = "standard",
):
    """Run the LRC visualizer main loop.

    On every track change the song's name is announced as a full-screen card —
    tinted with the album cover's dominant colour (white text on dark covers,
    dark text on light ones) — then its lyrics start in lock-step with the
    audio on the default terminal background, with music notes drifting behind
    them.

    Sync is closed-loop: a :class:`~lyrics_tool.sync.PlaybackClock` keeps a
    smooth estimate of the player's position and continuously eases itself onto
    fresh MPRIS samples fed by the monitor thread, so lyrics track the same
    timeline the desktop media widget shows instead of drifting off a single
    noisy anchor. Lines still flip on the monotonic clock between samples, so the
    player is never polled per frame.

    ``sync_offset`` shifts lyrics in seconds (positive = earlier, negative =
    later) and stacks on the built-in :data:`LYRIC_LEAD` plus any live nudge the
    user has saved. While playing, the ``+`` / ``-`` keys slide the lyrics in
    real time and persist the choice; ``0`` clears it.
    """
    from .visualizer_player import get_state, get_audio_file_info, get_art_url, is_ad
    from .visualizer_display import (
        display_lyrics, display_waiting, display_now_playing,
        display_now_playing_glitch, display_ad, display_searching, display_no_lyrics,
        get_terminal_size, hide_cursor, show_cursor, clear_screen,
        flash_sync, clear_sync_hud,
    )
    from .parser import parse_lrc_simple
    from .audio import find_lrc_for_audio
    from .theme_source import make_color_provider, NullColorProvider
    from .effects import NoteField, line_effect_color, effect_animating
    from .sync import PlaybackClock

    # Reveal effect: 'typewriter' drives the char-by-char line selection; 'fade' /
    # 'glow' are colour-only overlays applied per frame below; 'standard' is instant.
    effect = reveal or "standard"
    typewriter = effect == "typewriter"

    # Fixed part of the head-start: built-in lead + the pinned --offset. The live
    # +/- keys add a saved nudge on top (``user_nudge``); ``lead`` is always the
    # sum of the two and is recomputed whenever the nudge changes.
    base_lead = LYRIC_LEAD + sync_offset
    user_nudge = _load_saved_offset()
    lead = base_lead + user_nudge

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

    # Where colours come from. Default 'art' = portable album-art tint; the CLI
    # may inject any other source (pywal / caelestia / a JSON theme file) via
    # ``color_provider``. ``--no-cover-color`` forces colours off entirely.
    if not cover_color:
        color_provider = NullColorProvider()
    elif color_provider is None:
        color_provider = make_color_provider('art')

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

    # The smooth, self-correcting playback estimate every painted line reads
    # from. Fed fresh MPRIS samples each frame so it tracks the player's own
    # timeline instead of drifting off a single anchor.
    clock = PlaybackClock()

    def _anchor_clock(state):
        """Hard-set the clock from a fresh snapshot; mirror the paused flag."""
        paused = state.status == 'Paused'
        clock.reset(state.position, state.sampled_at, playing=not paused,
                    quantum=sync_data.quantum)
        sync_data.paused = paused

    # Live keyboard control (sync nudge). A no-op off a TTY; put the terminal in
    # cbreak on enter and always restore it in ``finally``.
    key_reader = KeyReader()
    key_reader.__enter__()

    try:
        last_title = None
        # Album-cover accent the current track's lyrics are painted in (None =
        # default terminal colour, e.g. cover_color off or art/Pillow missing).
        lyric_color = None
        # Card + lyric colours for the current track, filled by the colour
        # provider (album art off-thread, or a live theme file). Any field may
        # stay None, meaning "use the terminal default".
        color_holder = {'card_bg': None, 'card_fg': None, 'lyric': None}
        fetch_holder = None   # off-thread on-the-fly lyric fetch for the current track
        steady_until = 0.0    # monotonic instant the settled title card may hand off
        idle_phase = 0        # animation tick for the waiting / ad / searching screens

        def _notes_now():
            """Current ambient-note positions for an idle screen, or None."""
            if note_field is None:
                return None
            cols, rows = get_terminal_size()
            return note_field.positions(cols, rows, time.monotonic())

        def _sync_colors():
            """Pull the latest colours from the provider into the holders.

            Returns True when the lyric tint changed, so the caller can force a
            repaint. Cheap to call every frame: album-art is a resolved-flag
            check; theme files are an mtime-gated stat.
            """
            nonlocal lyric_color
            c = color_provider.current()
            if c is None:
                return False
            changed = c.lyric is not None and c.lyric != lyric_color
            if c.lyric is not None:
                lyric_color = c.lyric
                color_holder['lyric'] = c.lyric
            if c.card_bg is not None:
                color_holder['card_bg'] = c.card_bg
            if c.card_fg is not None:
                color_holder['card_fg'] = c.card_fg
            return changed

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
                _sync_colors()
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
                _sync_colors()
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
                _sync_colors()
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
                lyric_color = None
                color_holder['card_bg'] = color_holder['card_fg'] = color_holder['lyric'] = None
                color_provider.on_track(get_art_url() if cover_color else None)
                _sync_colors()  # continuous sources (theme files) land instantly
                display_now_playing_glitch(artist, title, font_data)
                display_now_playing(
                    artist, title, font_data,
                    bg=color_holder['card_bg'],
                    fg=color_holder['card_fg'],
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

            # Anchor the clock to a fresh, precise sample for the first line.
            state = get_state()
            if state is None or state.title != title:
                continue
            sync_data.current_title = title
            _anchor_clock(state)
            last_consumed = state.sampled_at   # newest sample folded into the clock
            sync_data.should_resync = False
            last_text = None
            last_tq = None
            last_idx = None                     # for reveal-effect line timing
            line_shown_at = time.monotonic()
            hud_until = 0.0                     # monotonic instant the sync HUD hides

            while sync_data.running:
                # Live sync nudge: +/- slide the lyrics earlier/later in real
                # time (and persist it), 0 clears it. No-op unless stdin is a TTY.
                # ('[' / ']' are avoided: they collide with arrow-key escapes.)
                key = key_reader.get()
                if key:
                    if key in ('+', '=', '.'):
                        user_nudge = min(5.0, round(user_nudge + NUDGE_STEP, 3))
                    elif key in ('-', '_', ','):
                        user_nudge = max(-5.0, round(user_nudge - NUDGE_STEP, 3))
                    elif key == '0':
                        user_nudge = 0.0
                    else:
                        key = None
                    if key:
                        lead = base_lead + user_nudge
                        _save_offset(user_nudge)
                        hud_until = time.monotonic() + 1.6

                # Big events (track change / pause / seek) flagged by the monitor
                # → jump the clock straight onto a fresh sample.
                if sync_data.should_resync:
                    sync_data.should_resync = False
                    snap = sync_data.latest
                    if snap is not None and snap.title != title:
                        break  # new song → outer loop reloads + re-announces
                    if snap is not None:
                        _anchor_clock(snap)
                        last_consumed = snap.sampled_at

                # Continuous fine correction: ease the clock toward each fresh
                # player sample so a noisy initial anchor can't leave the whole
                # song running early or late. Also self-heals a pause/resume the
                # monitor's flag happened to miss.
                snap = sync_data.latest
                if (snap is not None and snap.title == title
                        and snap.sampled_at != last_consumed):
                    last_consumed = snap.sampled_at
                    if snap.status == 'Paused':
                        if not clock.paused:
                            clock.pause(snap.position, quantum=sync_data.quantum)
                            sync_data.paused = True
                    elif clock.paused:
                        _anchor_clock(snap)          # resumed
                    else:
                        clock.correct(snap.position, snap.sampled_at,
                                      quantum=sync_data.quantum)

                # Current playback estimate. ``current_pos`` carries the lead for
                # line selection; typewriter reveal tracks the raw position so a
                # phrase isn't cut off before it finishes typing.
                play = clock.position()
                current_pos = play + lead
                line_pos = play if typewriter else current_pos

                # Pick the line for now — recomputed each frame so a gentle
                # correction that nudges us back across a boundary is honoured,
                # not just forward motion.
                idx = _index_for(lines, line_pos)
                # Never step back a line for a sliver of clock correction: a
                # few frames of the previous line reads as a flicker. A real
                # seek backwards moves further than this and still goes through.
                if (last_idx is not None and 0 <= idx < last_idx
                        and line_pos > lines[last_idx][0] - BACKSTEP_TOLERANCE):
                    idx = last_idx

                text = '' if idx < 0 else lines[idx][1]

                # Note when the visible line changes — the reveal effects (fade /
                # glow) time their animation from this instant.
                if idx != last_idx:
                    last_idx = idx
                    line_shown_at = time.monotonic()

                # Typewriter: progressively reveal the line character-by-character.
                # Uses line_pos (raw playback position without the lyric lead) so
                # the reveal tracks the actual vocal exactly.
                tw_display = text
                if typewriter and text and idx >= 0:
                    line_start = lines[idx][0]
                    line_end = (lines[idx + 1][0]
                                if idx + 1 < len(lines)
                                else line_start + 5.0)
                    tw_span = max(0.01, line_end - line_start)
                    tw_progress = min(1.0, max(0.0,
                                               (line_pos - line_start) / tw_span))
                    chars_to_show = min(len(text),
                                        int(len(text) * tw_progress + 0.5))
                    # Solid cursor when paused (frozen); blink at 3 Hz while playing.
                    if sync_data.paused:
                        tw_cursor = '▌'
                    else:
                        tw_cursor = '▌' if int(time.monotonic() * 3) % 2 == 0 else ' '
                    if chars_to_show < len(text):
                        tw_display = text[:chars_to_show] + tw_cursor
                    else:
                        tw_display = text

                # Recompose only when the line or the note layer actually
                # changes — the notes tick on a quantised clock so we don't
                # rebuild (or repaint) the frame every spin.
                note_positions = None
                tq = None
                if note_field is not None:
                    tq = int(time.monotonic() / NOTE_DT)
                # Pick up colours the moment they change — the album-art fetch
                # landing, or a live desktop-theme switch under our feet.
                if _sync_colors():
                    last_text = None  # force a repaint in the new colour

                # Premium reveal effect: recolour the line as it fades in / glows.
                # 'standard'/'typewriter' leave the colour untouched (eff == base)
                # and never keep the frame animating.
                elapsed = time.monotonic() - line_shown_at
                eff_color = line_effect_color(lyric_color, effect, elapsed, sync_data.paused)
                animating = effect_animating(effect, elapsed)

                # In typewriter mode the visible portion changes every tick, so we
                # compare the display string rather than the source text; while an
                # effect animates we repaint every frame so the colour keeps moving.
                cmp_text = tw_display if typewriter else text
                if cmp_text != last_text or tq != last_tq or animating:
                    last_text, last_tq = cmp_text, tq
                    if note_field is not None:
                        cols, rows = get_terminal_size()
                        note_positions = note_field.positions(cols, rows, tq * NOTE_DT)
                    display_lyrics(tw_display, font_data=font_data, notes=note_positions,
                                   color=eff_color)

                # Live sync HUD: sits on the bottom row via save/restore cursor
                # (outside the frame diff), repainted each frame while up so a
                # lyric repaint can't scrub it, then cleared once when it expires.
                if hud_until:
                    if time.monotonic() > hud_until:
                        clear_sync_hud()
                        hud_until = 0.0
                    else:
                        flash_sync(lead, lyric_color)

                # Spin slower while paused — nothing advances, so save CPU.
                # In typewriter mode keep a snappy tick even when paused so the
                # UI stays responsive to resume/seek.
                if sync_data.paused:
                    time.sleep(refresh_rate if typewriter else 0.3)
                else:
                    time.sleep(refresh_rate)

    except KeyboardInterrupt:
        pass
    finally:
        sync_data.running = False
        key_reader.__exit__(None, None, None)
        show_cursor()
        clear_screen()
