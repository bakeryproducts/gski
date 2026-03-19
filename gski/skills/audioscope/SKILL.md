---
name: gski audioscope
description: Transcribe and diarize audio — speech-to-text, speaker identification, timestamps
---

## Setup

Check: `which gski`
Install if missing: `pip install gski` (from the gski repo)
Requires `GEMINI_API_KEY` env var.

## How it works

`gski audioscope` sends audio files or YouTube URLs to Gemini and returns transcriptions. Supports speaker diarization (who said what) and timestamped segments via structured output.

Default model is `gemini-3-flash-preview`. For higher quality: `--model pro`.

Files under 15 MB are sent inline. Larger files are uploaded via the Files API automatically.

## Commands

```bash
# Plain transcription
gski audioscope --audio meeting.mp3

# Transcription with timestamps
gski audioscope --audio meeting.mp3 --timestamps

# Speaker diarization
gski audioscope --audio meeting.mp3 --diarize

# Diarization with timestamps
gski audioscope --audio meeting.mp3 --diarize --timestamps

# YouTube URL
gski audioscope --youtube "https://www.youtube.com/watch?v=..."

# Custom prompt
gski audioscope "summarize the key decisions" --audio meeting.mp3

# Multiple audio files
gski audioscope --audio part1.mp3 --audio part2.mp3 --diarize
```

## Options

| Flag | Values | Default | Notes |
|------|--------|---------|-------|
| `prompt` | positional, optional | auto-selected | overrides default prompt |
| `--audio FILE` | repeatable | none | local audio file(s) |
| `--youtube URL` | repeatable | none | YouTube URL(s) |
| `--model` | `flash`, `pro` | `flash` | model selection |
| `--diarize` | flag | off | speaker identification (JSON output) |
| `--timestamps` | flag | off | add MM:SS timestamps to segments |
| `--output-dir` | path | `./output` | where to save output files |

## Output

- **Default mode**: plain transcript text to stdout, saved as `.txt`
- **`--diarize`**: formatted speaker-labeled transcript to stdout, structured JSON saved to `--output-dir`
- **`--timestamps`**: timestamps included in output segments
- All output files saved to `--output-dir` (created automatically)

## Supported formats

WAV, MP3, AIFF, AAC, OGG, FLAC

## Notes

- At least one `--audio` or `--youtube` is required
- `--diarize` and `--timestamps` can be combined
- Files over 15 MB are automatically uploaded via Gemini Files API
- Max audio length per prompt: 9.5 hours
- Gemini downsamples to 16 Kbps, merges multi-channel to mono
- ~32 tokens per second of audio
