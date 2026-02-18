# gski

Pip-installable Python package. Bundles skill scripts (CLI tools) and their OpenCode SKILL.md files.

## Structure

```
gski/
├── pyproject.toml
└── gski/
    ├── cli.py              # entry point: gski <command>
    ├── nanobanana.py       # gski nanobanana — Gemini image gen/edit
    ├── nanoscope.py        # gski nanoscope — Gemini image understanding
    ├── setup.py            # gski setup <dir> — copy SKILL.md files
    └── skills/
        ├── nanobanana/
        │   └── SKILL.md
        └── nanoscope/
            └── SKILL.md
```

## CLI

```
gski nanobanana "prompt" [--image FILE]... [--model flash|pro] [--aspect-ratio RATIO] [--size 1K|2K|4K] [--search] [--output-dir DIR]
gski nanoscope "prompt" --image FILE [--url URL]... [--model flash|pro] [--detect] [--segment] [--output-dir DIR]
gski setup <target-dir>
```

## Adding a new skill

1. Create `gski/<skillname>.py` with `register(subparsers)` and `run(args)`
2. Import and call `register()` in `cli.py`
3. Add `gski/skills/<skillname>/SKILL.md`

## Dependencies

- `google-genai` — Gemini API SDK
- `Pillow` — image handling
- Requires `GEMINI_API_KEY` env var

## Install

```
pip install -e .
```
