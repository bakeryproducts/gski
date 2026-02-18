import sys
from importlib.resources import files
from pathlib import Path


def register(subparsers):
    p = subparsers.add_parser("setup", help="copy SKILL.md files to target directory")
    p.add_argument(
        "target_dir", help="directory to copy skills into (e.g. opencode/skills)"
    )
    p.set_defaults(func=run)


def run(args):
    skills_dir = files("gski") / "skills"
    target = Path(args.target_dir)

    count = 0
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        dest = target / skill_name
        dest.mkdir(parents=True, exist_ok=True)
        for f in skill_dir.iterdir():
            src_data = f.read_text()
            dst = dest / f.name
            dst.write_text(src_data)
            count += 1
            print(f"  {dst}")

    if count == 0:
        print("no skills found", file=sys.stderr)
        sys.exit(1)

    print(f"\n{count} file(s) copied to {target}")
