from __future__ import annotations

import argparse
import asyncio
import bisect
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
import re
import time
import unicodedata

import requests
import yaml
from rich.console import Console
from rich.live import Live
from rich.text import Text
from unidecode import unidecode

BASE = Path(__file__).resolve().parent
LYRICS_DIR = BASE / 'lyrics'
API = 'https://lrclib.net/api/search'
HEADERS = {'User-Agent': 'LyricsPrinter/5.0 (personal-use music display)'}
POLL = 0.085
OFFSET_SECONDS = 0.0  # positive = lyrics earlier, negative = later
COLORS = ['bright_cyan', 'bright_magenta', 'bright_green', 'bright_yellow', 'bright_blue', 'bright_red']
console = Console()


@dataclass(frozen=True)
class Word:
    at: float
    value: str


@dataclass(frozen=True)
class Line:
    at: float
    value: str
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class Lyrics:
    lines: tuple[Line, ...]
    word_synced: bool
    source: str


def normalized(value: str | None) -> str:
    s = unicodedata.normalize('NFKC', value or '').casefold().replace('&', ' and ')
    return ' '.join(''.join(c if unicodedata.category(c)[0] in 'LMN' else ' ' for c in s).split())


def romanize(text: str) -> str:
    if not text:
        return ''
    if not any(ord(ch) > 127 and ch.isalpha() for ch in text):
        return text.strip()
    out = unidecode(text).strip()
    if any('\u0900' <= c <= '\u097f' for c in text):
        # Devanagari: remove length markers for familiar casual Hindi writing.
        out = re.sub('ii', 'i', out, flags=re.I)
        out = re.sub('uu', 'u', out, flags=re.I)
        out = re.sub(r'N\b', 'n', out)
    if any('\u0980' <= c <= '\u09ff' for c in text):
        out = out.replace("'", '')
        out = re.sub('aa', 'a', out, flags=re.I)
        out = re.sub('ii', 'i', out, flags=re.I)
        out = re.sub('uu', 'u', out, flags=re.I)
    return re.sub(r'\s+', ' ', out).strip()


def clean_title(s: str) -> str:
    s = (s or '').strip().lstrip('@#').strip()
    s = re.sub(r'\((?:official|lyrics?|audio|video|full song|lyrical)[^)]*\)', ' ', s, flags=re.I)
    s = re.sub(r'\[(?:official|lyrics?|audio|video|full song|lyrical)[^]]*\]', ' ', s, flags=re.I)
    s = re.sub(r'\b(?:official (?:music )?video|official audio|lyrical (?:video|song)|lyrics video|full (?:video )?song|video song|audio song|with lyrics|hd video|4k)\b', ' ', s, flags=re.I)
    s = re.sub(r'^(?:song|music video|lyrical)\s*:\s*', '', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' -|:._')


def generic_uploader(s: str) -> bool:
    return bool(re.search(r't.series|sony\s*music|vevo|coke\s*studio|zee\s*music|saregama|tips\s*official|\blyrics?\b|records|official|topic|music\s*(india|world|channel|company)', s, re.I))


def title_metadata(video_title: str, uploader: str) -> tuple[str, str]:
    title = clean_title(video_title)
    parts = [clean_title(p) for p in re.split(r'\s*\|\s*', title)]
    parts = [p for p in parts if p]
    if len(parts) >= 3 and re.search('coke studio', parts[0], re.I):
        return parts[1], parts[2]
    if len(parts) >= 2 and re.search('coke studio', parts[0], re.I):
        return parts[1], ''
    if len(parts) >= 2:
        # Typical Bollywood YouTube: "Tum Hi Ho | Aashiqui 2 | Arijit Singh"
        guesses = [p for p in parts[1:] if re.search(r'\b(?:arijit|atif|shreya|sonu|jubin|neha|rahat|kk|sunidhi|kishore|lata|udit|b\s*praak|darshan|kaavish)\b', p, re.I)]
        return parts[0], (guesses[0] if guesses else ('' if generic_uploader(uploader) else clean_title(uploader)))
    if re.search(r'\s[-–—]\s', title):
        left, right = re.split(r'\s[-–—]\s', title, maxsplit=1)
        return clean_title(right), clean_title(left)
    return title, '' if generic_uploader(uploader) else clean_title(uploader)


def parse_lrc(source: str) -> Lyrics | None:
    delay = re.search(r'^\[offset\s*:\s*([+-]?\d+)\]', source or '', re.M | re.I)
    offset = int(delay.group(1)) / 1000.0 if delay else 0.0
    pat = re.compile(r'\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]')
    lines = []
    for raw in (source or '').splitlines():
        matches = list(pat.finditer(raw))
        if not matches:
            continue
        content = pat.sub('', raw).strip()
        for match in matches:
            at = max(0, int(match.group(1)) * 60 + float(match.group(2)) + offset)
            lines.append(Line(at, content))
    return Lyrics(tuple(sorted(lines, key=lambda item: item.at)), False, 'LRC') if lines else None


def parse_lyricsfile(raw: str) -> Lyrics | None:
    try:
        document = yaml.safe_load(raw)
        if not isinstance(document, dict) or not isinstance(document.get('lines'), list):
            return None
        lines = []
        has_words = False
        for item in document['lines']:
            if not isinstance(item, dict):
                continue
            words = []
            for word in item.get('words') or []:
                if not isinstance(word, dict) or word.get('start_ms') is None:
                    continue
                text = str(word.get('text') or '').strip()
                if text:
                    words.append(Word(max(0.0, float(word['start_ms']) / 1000.0), romanize(text)))
            text = str(item.get('text') or '').strip()
            if item.get('start_ms') is None and not words:
                continue
            at = float(item['start_ms']) / 1000.0 if item.get('start_ms') is not None else words[0].at
            at = max(0.0, at)
            if words:
                has_words = True
            lines.append(Line(at, romanize(text) if text else ' '.join(w.value for w in words), tuple(words)))
        if lines:
            return Lyrics(tuple(sorted(lines, key=lambda x: x.at)), has_words, 'Lyricsfile')
    except (yaml.YAMLError, TypeError, ValueError, OverflowError):
        pass
    return None


def from_record(record: dict) -> Lyrics | None:
    if record.get('instrumental'):
        return None
    if record.get('hasWordSync') and record.get('lyricsfile'):
        value = parse_lyricsfile(record['lyricsfile'])
        if value and value.word_synced:
            return value
    if record.get('syncedLyrics'):
        value = parse_lrc(record['syncedLyrics'])
        if value:
            return value
    if record.get('lyricsfile'):
        return parse_lyricsfile(record['lyricsfile'])
    return None


def variants(value: str) -> list[str]:
    result = []
    for x in (value, romanize(value), unidecode(value).strip()):
        if normalized(x) and normalized(x) not in {normalized(k) for k in result}:
            result.append(x)
    return result


def similarity(left: str, right: str) -> float:
    best = 0.0
    for a in variants(left):
        for b in variants(right):
            x, y = normalized(a), normalized(b)
            if not x or not y:
                continue
            if x == y:
                return 1.0
            if len(x) >= 5 and x in y:
                best = max(best, 0.93)
            elif len(y) >= 5 and y in x:
                best = max(best, 0.90)
            else:
                best = max(best, SequenceMatcher(None, x, y).ratio())
    return best


def match_score(title: str, artist: str, duration: float, record: dict) -> float:
    if not isinstance(record, dict) or record.get('instrumental'):
        return -1
    # A Lyricsfile may contain only plain lyrics: it must have timed lines.
    if not record.get('syncedLyrics') and not (record.get('hasWordSync') and record.get('lyricsfile')):
        parsed = parse_lyricsfile(record.get('lyricsfile') or '')
        if not parsed or not parsed.lines:
            return -1
    title_score = similarity(title, str(record.get('trackName') or ''))
    if title_score < 0.77:
        return -1
    artist_score = similarity(artist, str(record.get('artistName') or '')) if artist else 0
    other_length = float(record.get('duration') or 0)
    difference = abs(duration - other_length) if duration > 0 and other_length > 0 else 0.0
    if difference > max(60.0, duration * 0.25):
        return -1
    return 100 * title_score + 15 * artist_score - min(30.0, 0.3 * difference) + (5 if record.get('hasWordSync') else 0)


def get_lyrics(title: str, artist: str, duration: float) -> Lyrics | None:
    if LYRICS_DIR.exists():
        targets = {normalized(title), normalized(f'{artist} - {title}')}
        targets |= {normalized(v) for v in variants(title)}
        for path in sorted(LYRICS_DIR.iterdir()):
            if not path.is_file():
                continue
            suffix = '.lyricsfile.yaml' if path.name.endswith('.lyricsfile.yaml') else path.suffix.lower()
            if suffix not in ('.lrc', '.lyricsfile.yaml'):
                continue
            stem = path.name[:-len(suffix)]
            if normalized(stem) not in targets:
                continue
            try:
                raw = path.read_text(encoding='utf-8-sig')
                lyrics = parse_lrc(raw) if suffix == '.lrc' else parse_lyricsfile(raw)
                if lyrics:
                    return Lyrics(lyrics.lines, lyrics.word_synced, f'Local: {path.name}')
            except (OSError, UnicodeError):
                continue

    requests_to_try = []
    for candidate_title in variants(title):
        requests_to_try.append({'track_name': candidate_title})
        if artist:
            requests_to_try.append({'q': f'{candidate_title} {romanize(artist)}'})
    # Try a short title search (works when the uploader isn't the recording artist).
    if len(title.split()) > 4:
        requests_to_try.append({'track_name': ' '.join(title.split()[:4])})
    best, best_score = None, 76.0
    seen = set()
    for i, query in enumerate(requests_to_try[:6]):
        key = tuple(sorted(query.items()))
        if key in seen:
            continue
        seen.add(key)
        if i:
            time.sleep(0.30)  # Be considerate of LRCLIB limits.
        try:
            response = requests.get(API, params=query, headers=HEADERS, timeout=9)
            if response.status_code == 429:
                break
            response.raise_for_status()
            records = response.json()
            if not isinstance(records, list):
                continue
        except (requests.RequestException, ValueError):
            continue
        for record in records:
            score = match_score(title, artist, duration, record)
            if score > best_score:
                best, best_score = record, score
        if best_score >= 117:
            break
    return from_record(best) if best else None


def word_schedule(lyrics: Lyrics, index: int) -> tuple[Word, ...]:
    line = lyrics.lines[index]
    if line.words:
        return line.words
    tokens = re.findall(r'\S+', romanize(line.value))
    if not tokens:
        return ()
    next_start = lyrics.lines[index + 1].at if index + 1 < len(lyrics.lines) else line.at + 5.0
    span = min(8.0, max(0.1, next_start - line.at) * 0.85)
    weights = [max(1, len(token.strip('.,!?-'))) for token in tokens]
    total = sum(weights)
    elapsed = 0
    result = []
    for token, weight in zip(tokens, weights):
        result.append(Word(line.at + span * elapsed / total, token))
        elapsed += weight
    return tuple(result)


def frame_for(lyrics: Lyrics, position: float) -> tuple[int, int]:
    times = [line.at for line in lyrics.lines]
    idx = bisect.bisect_right(times, position + OFFSET_SECONDS) - 1
    if idx < 0:
        return -1, 0
    line = lyrics.lines[idx]
    if not line.value and not line.words:
        return idx, 0
    words = word_schedule(lyrics, idx)
    count = bisect.bisect_right([word.at for word in words], position + OFFSET_SECONDS)
    return idx, count


def draw_line(lyrics: Lyrics, index: int, visible: int, cursor=True) -> Text:
    line = lyrics.lines[index]
    out = Text()
    out.append(f'[{int(line.at // 60):02}:{line.at % 60:05.2f}] ', 'dim')
    out.append('♪ ', 'bold bright_yellow')
    words = word_schedule(lyrics, index)
    for i, word in enumerate(words[:visible]):
        if i:
            out.append(' ')
        out.append(word.value, style=f'bold {COLORS[(index + i) % len(COLORS)]}')
    if cursor and visible < len(words):
        out.append(' ▍', 'bright_white')
    return out


def get_session(manager):

    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    current = manager.get_current_session()
    sessions = list(manager.get_sessions())
    if current:
        sessions.insert(0, current)
    paused = None
    seen = set()
    for session in sessions:
        identifier = session.source_app_user_model_id
        if identifier in seen:
            continue
        seen.add(identifier)
        try:
            info = session.get_playback_info()
            if info is None:
                continue
            if info.playback_status == Status.PLAYING:
                return session, info, True
            if paused is None and info.playback_status == Status.PAUSED:
                paused = (session, info, False)
        except (OSError, RuntimeError):
            continue
    return paused if paused else (None, None, False)


def media_position(session, playback, playing: bool) -> tuple[float, float, bool]:
    timeline = session.get_timeline_properties()
    seconds = max(0.0, timeline.position.total_seconds())
    duration = max(0.0, timeline.end_time.total_seconds())
    last = timeline.last_updated_time
    valid = bool(last and 2000 <= last.year <= 2100)
    if valid and playing:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if 0 <= elapsed < 900:
            speed = playback.playback_rate
            seconds += elapsed * max(0.0, float(speed) if speed is not None else 1.0)
        else:
            valid = False
    if duration:
        seconds = min(seconds, duration)
    return seconds, duration, valid


async def run_live(args):
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    manager = await MediaManager.request_async()
    console.print('[bold bright_magenta]♫ LIVE WORD-SYNC LYRICS — HINDI / BANGLISH ♫[/bold bright_magenta]')
    console.print('[dim]Words follow Windows media time. Ctrl+C to exit.[/dim]')
    identity = None
    lookup = None
    lyrics = None
    current_idx = -1
    current_count = -1
    last_position = None
    last_wall = None
    status = ''
    with Live(Text('♪ Waiting for music...', style='dim'), console=console, transient=True, auto_refresh=False) as live:
        while True:
            try:
                session, playback, playing = get_session(manager)
                if not session:
                    if status != 'waiting':
                        live.update(Text('♪ Waiting for an active player...', style='yellow'), refresh=True)
                        status = 'waiting'
                    await asyncio.sleep(0.25)
                    continue
                media = await session.try_get_media_properties_async()
                original_title = (media.title or '').strip()
                uploader = (media.artist or '').strip()
                if not original_title:
                    await asyncio.sleep(0.2)
                    continue
                ident = (session.source_app_user_model_id, original_title, uploader)
                position, duration, valid = media_position(session, playback, playing)
                if ident != identity:
                    if lookup:
                        lookup.cancel()
                    identity = ident
                    lyrics = None
                    current_idx = current_count = -1
                    last_position = last_wall = None
                    title, artist = title_metadata(original_title, uploader)
                    title = args.title or title
                    artist = args.artist or artist
                    console.print(f'\n[bold cyan]♫ {title}[/bold cyan] [dim]— {artist or "unknown artist"}[/dim]')
                    console.print(f'[dim]YouTube / player title: {original_title}[/dim]')
                    live.update(Text('Searching timed lyrics...', style='cyan'), refresh=True)
                    lookup = asyncio.create_task(asyncio.to_thread(get_lyrics, title, artist, duration))
                if lookup and lookup.done():
                    try:
                        lyrics = lookup.result()
                    except (asyncio.CancelledError, Exception) as error:
                        console.print(f'[yellow]Lookup failed: {error}[/yellow]')
                        lyrics = None
                    lookup = None
                    if lyrics:
                        accuracy = 'EXACT WORD TIMESTAMPS' if lyrics.word_synced else 'ESTIMATED WORD SPACING (line-timed LRC)'
                        console.print(f'[green]{len(lyrics.lines)} timed lines • {accuracy} • {lyrics.source}[/green]')
                    else:
                        live.update(Text('No matching timed lyrics found. Try --title / --artist or a local .lrc file.', style='yellow'), refresh=True)
                if lyrics:
                    position, _, valid = media_position(session, playback, playing)
                    index, count = frame_for(lyrics, position)
                    now = time.monotonic()
                    seek = False
                    if last_position is not None and last_wall is not None:
                        expected = max(0.0, now - last_wall) * (float(playback.playback_rate or 1) if playing else 0)
                        seek = abs((position - last_position) - expected) > 1.8
                    if (index, count) != (current_idx, current_count) or status == 'waiting':
                        # Print a completed line only on a natural transition, never when seeking.
                        if index != current_idx and current_idx >= 0 and not seek:
                            old_line = lyrics.lines[current_idx]
                            if old_line.value:
                                console.print(draw_line(lyrics, current_idx, len(word_schedule(lyrics, current_idx)), cursor=False))
                        if index < 0 or not lyrics.lines[index].value:
                            live.update(Text('♪ Instrumental / waiting for next lyric...', style='dim'), refresh=True)
                        else:
                            live.update(draw_line(lyrics, index, count), refresh=True)
                        current_idx, current_count = index, count
                        status = 'lyric'
                    last_position, last_wall = position, now
                await asyncio.sleep(POLL)
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                live.update(Text(f'Player updated: {exc}', style='yellow'), refresh=True)
                await asyncio.sleep(0.5)


async def demo():
    demo_yaml = '''version: '1.0'
lines:
  - text: 'तुम ही हो'
    start_ms: 700
    words:
      - {text: 'तुम', start_ms: 700}
      - {text: 'ही', start_ms: 1350}
      - {text: 'हो', start_ms: 2000}
  - text: 'আমি তোমায় ভালোবাসি'
    start_ms: 3000
    words:
      - {text: 'আমি', start_ms: 3000}
      - {text: 'তোমায়', start_ms: 3700}
      - {text: 'ভালোবাসি', start_ms: 4500}
  - text: 'Hear the music flow'
    start_ms: 5700
'''
    lyrics = parse_lyricsfile(demo_yaml)
    assert lyrics is not None
    console.print('[bold cyan]DEMO — words follow playback position; switching to 1.5× speed halfway[/bold cyan]')
    clock = time.monotonic()
    previous = (-1, -1)
    last_index = -1
    with Live(Text('♪ Waiting...', style='dim'), console=console, transient=True, auto_refresh=False) as live:
        while True:
            elapsed = time.monotonic() - clock
            pos = elapsed if elapsed <= 3.6 else 3.6 + 1.5 * (elapsed - 3.6)
            if pos > 9.0:
                break
            index, count = frame_for(lyrics, pos)
            if (index, count) != previous:
                if index != last_index and last_index >= 0:
                    console.print(draw_line(lyrics, last_index, len(word_schedule(lyrics, last_index)), cursor=False))
                if index >= 0:
                    live.update(draw_line(lyrics, index, count), refresh=True)
                previous = (index, count)
                last_index = index
            await asyncio.sleep(0.06)
        if last_index >= 0:
            console.print(draw_line(lyrics, last_index, len(word_schedule(lyrics, last_index)), cursor=False))
    console.print('[green]Demo finished.[/green]')


async def diagnose():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    manager = await MediaManager.request_async()
    console.print('Diagnostics — please play a Hindi song for this test')
    for _ in range(10):
        session, playback, playing = get_session(manager)
        if session:
            media = await session.try_get_media_properties_async()
            position, duration, valid = media_position(session, playback, playing)
            title, artist = title_metadata(media.title or '', media.artist or '')
            console.print(f'Player title={media.title!r} artist={media.artist!r}\n'
                          f'  parsed={title!r} / {artist!r} position={position:.2f}s '
                          f'duration={duration:.1f}s speed={playback.playback_rate} '
                          f'playing={playing} timeline_valid={valid}')
        else:
            console.print('No media session found')
        await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description='Colorful Windows synchronized lyric word printer')
    parser.add_argument('--demo', action='store_true', help='Offline demo with speed change')
    parser.add_argument('--diagnose', action='store_true', help='Inspect playback info')
    parser.add_argument('--title', help='Override badly detected YouTube song title')
    parser.add_argument('--artist', help='Override artist for better Hindi matching')
    args = parser.parse_args()
    try:
        if args.demo:
            asyncio.run(demo())
        elif args.diagnose:
            asyncio.run(diagnose())
        else:
            asyncio.run(run_live(args))
    except KeyboardInterrupt:
        console.print('\n[dim]Stopped.[/dim]')


if __name__ == '__main__':
    main()
