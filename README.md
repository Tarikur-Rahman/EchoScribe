<div align="center">

# 🎶 EchoScribe

**Turn what's playing into colorful, synchronized lyrics in your terminal.**

A Python-powered Windows lyrics visualizer that detects the active media session, finds timestamped lyrics, and reveals words as the music plays. Supports multilingual lyrics in Latin letters, including **Banglish** and **Romanized Hindi**.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D4?logo=windows&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-Terminal-222222)

</div>

---

## ✨ Features

- **Now-playing detection:** Reads track metadata and playback position from supported Windows media players (including browsers or Spotify when they expose a media session).
- **Playback-aware lyrics:** Follows the reported song position, playback-rate changes, pausing, and seeking.
- **Animated words:** Displays colorful words progressively in the terminal instead of dumping entire lyrics at once.
- **Two timing modes:** Uses real word timestamps when available, or estimates the spacing of words from line-level LRC timestamps.
- **Multilingual romanization:** Converts Bengali script to approximate **Banglish**, Devanagari to **Romanized Hindi**, and other supported scripts to Latin characters, without translating the meaning.
- **Smarter song search:** Cleans some YouTube video titles and searches for matched synchronized lyrics; manual title/artist overrides help with difficult tracks.
- **Offline demo and local lyric support:** Try the animation without a song, or load your own timed `.lrc` / `.lyricsfile.yaml` files.

## 🖥️ Example output

*Illustrative text, not lyrics from a commercial recording.*

```text
♫ LIVE WORD-SYNC LYRICS — HINDI / BANGLISH ♫

♫ Example Track — Example Artist
34 timed lines • ESTIMATED WORD SPACING (line-timed LRC)

[00:12.50] ♪ Ami tomay bhalobashi
[00:16.20] ♪ Tumi amar bondhu
```

Colors and live word-reveal animation appear in a compatible terminal; a plain text capture will not reproduce them.

## 🛠️ Tech stack

| Technology | Purpose |
| --- | --- |
| Python 3.11+ | Application and asynchronous playback loop |
| Windows Media Control / WinRT | Now-playing metadata, playback position, and playback rate |
| [LRCLIB](https://lrclib.net/) | Online lookup for synchronized lyrics |
| [Rich](https://github.com/Textualize/rich) | Colorful, continuously updated terminal display |
| [Requests](https://requests.readthedocs.io/) | Lyrics API requests |
| [PyYAML](https://pyyaml.org/) | Reading word-timed Lyricsfile YAML |
| [Unidecode](https://pypi.org/project/Unidecode/) | Approximate Latin-script romanization |

## 📁 Project structure

```text
EchoScribe/
├── lyricsprinter.py       # Main application
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
└── lyrics/                # Optional local timestamped lyrics
```

The `lyrics/` folder is optional. You can create it yourself; do not commit song lyrics you do not have permission to distribute.

## 🚀 Installation (Windows)

**Prerequisites:** Windows 10/11, Python 3.11 or newer, Git, and a terminal that supports ANSI colors (Windows Terminal, Git Bash, or VS Code terminal). An internet connection is needed to look up lyrics online.

1. Clone the repository and enter its folder:

   ```bash
   git clone https://github.com/Tarikur-Rahman/EchoScribe.git
   cd EchoScribe
   ```

2. Create and activate a virtual environment (Git Bash):

   ```bash
   python -m venv .venv
   source .venv/Scripts/activate
   ```

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

> Make sure `lyricsprinter.py` and `requirements.txt` are present in the repository before following these commands.

## ▶️ Usage

**Try the colorful offline demo:**

```bash
python -u lyricsprinter.py --demo
```

**Follow music currently playing on your laptop:**

```bash
python -u lyricsprinter.py
```

Start playback in a supported application, then leave the script running. Press **Ctrl+C** to stop.

**Troubleshoot song detection and timing:**

```bash
python -u lyricsprinter.py --diagnose
```

**Correct incorrect YouTube metadata (example):**

```bash
python -u lyricsprinter.py --title "Tum Hi Ho" --artist "Arijit Singh"
```

Overrides apply to the song being tested; omit them to detect other tracks automatically.

## 🌍 Language handling

EchoScribe **romanizes** lyrics; it does not translate their meaning into English.

| Original script | Terminal output (approximate) |
| --- | --- |
| Bengali: `আমি তোমায় ভালোবাসি` | `Ami tomay bhalobasi` |
| Hindi: `तुम ही हो` | `Tum hi ho` |
| English: `Hear the music flow` | `Hear the music flow` |

Romanization quality varies by language, dialect, spelling, and the accuracy of the available lyrics. Support for a writing system does not guarantee that a particular song is available in the lyrics database.

## ⏱️ How synchronization works

1. Windows identifies a playing media session and reports its playback position and rate.
2. EchoScribe searches for timestamped lyrics (or reads a matching local file).
3. For **word-timed Lyricsfile** entries, each word appears at its supplied timestamp.
4. For **line-timed LRC**, the program estimates word timing within each line. This looks like karaoke but is **not guaranteed to match the singer's exact words**.
5. A pause freezes the reveal; seeking moves the display to the corresponding point in the track, if the player reports a usable timeline.

The script does **not** listen to or transcribe laptop audio. Accurate results depend on the selected lyrics matching the exact song recording.

### Use your own local synchronized lyrics

Create a `lyrics/` folder next to `lyricsprinter.py`. Name a file after the detected track title, such as `Example Track.lrc`:

```text
[00:04.00] This is an original example line
[00:07.50] Here comes the next example line
```

For actual word timestamps, use `Example Track.lyricsfile.yaml`:

```yaml
version: '1.0'
lines:
  - text: The music begins
    start_ms: 4000
    words:
      - {text: The, start_ms: 4000}
      - {text: music, start_ms: 4600}
      - {text: begins, start_ms: 5300}
```

Both examples contain original placeholder lyrics. The program also accepts local `.lrc` files with Bengali or Hindi script and attempts to render them in Latin letters.

## ⚙️ Configuration

In `lyricsprinter.py`:

```python
OFFSET_SECONDS = 0.0  # positive = show lyrics earlier; negative = later
POLL = 0.085          # seconds between display checks
```

If lyrics consistently appear late, try a small positive `OFFSET_SECONDS` (for example `0.3`). If they appear early, use a negative value. This adjusts timing but cannot correct the wrong lyric version.

## 🔎 Troubleshooting

| Problem | What to check |
| --- | --- |
| `ModuleNotFoundError` | Install packages using `python -m pip install -r requirements.txt` with the same Python interpreter used to run the script. |
| No song detected | Start playback in a supported app; run `--diagnose` and check Windows media session metadata. |
| No matching timed lyrics | Try `--title` and `--artist`, or provide a matching local `.lrc` / `.lyricsfile.yaml` file. |
| Hindi/Bengali song not found | Check the actual track title and performer; YouTube channel names are not always recording-artist names. |
| Words appear too early/late | Check song version, player timeline, lyric timestamps, and `OFFSET_SECONDS`. |
| All words appear at once | Ensure you are running the current `lyricsprinter.py`, not an older copy, and that timestamped lyric data is available. |

## ⚠️ Limitations and responsible use

- **Windows only:** The current detection implementation uses Windows media APIs.
- **Not universal:** Some media players do not publish usable metadata or playback positions.
- **Lyrics availability varies:** Not every song or language has correctly timed lyrics online.
- **Word-level precision is conditional:** With line-level LRC, word animation is an estimate; real word-accurate timing requires word timestamps.
- **External data:** Online lyrics lookup uses LRCLIB and needs network access. Local timed lyrics can work offline.
- **Copyright:** This repository should contain application code and documentation, not copyrighted lyric collections or recordings unless you have the necessary rights.

## 👨‍💻 Author

**Md. Tarikur Rahman**  
GitHub: [@Tarikur-Rahman](https://github.com/Tarikur-Rahman)

---

<div align="center">

**EchoScribe — Watch the words move with the music.** 🎵

</div>
