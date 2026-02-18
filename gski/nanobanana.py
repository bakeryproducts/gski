import os
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image


MODELS = {
    "flash": "gemini-2.5-flash-image",
    "pro": "gemini-3-pro-image-preview",
}

ASPECT_RATIOS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]
SIZES = ["1K", "2K", "4K"]


def build_config(args):
    kwargs = {}

    if args.model == "pro":
        kwargs["response_modalities"] = ["TEXT", "IMAGE"]

    image_config_kwargs = {}
    if args.aspect_ratio:
        image_config_kwargs["aspect_ratio"] = args.aspect_ratio
    if args.size and args.model == "pro":
        image_config_kwargs["image_size"] = args.size

    if image_config_kwargs:
        kwargs["image_config"] = types.ImageConfig(**image_config_kwargs)

    if args.search:
        kwargs["tools"] = [{"google_search": {}}]

    if not kwargs:
        return None
    return types.GenerateContentConfig(**kwargs)


def build_contents(prompt, image_paths):
    contents = [prompt]
    for p in image_paths:
        contents.append(Image.open(p))
    return contents


def save_images(response, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    img_idx = 0

    for part in response.parts:
        if part.thought:
            continue
        if part.text is not None:
            print(part.text)
        elif part.inline_data is not None:
            suffix = f"_{img_idx}" if img_idx > 0 else ""
            filename = f"{ts}{suffix}.png"
            filepath = output_dir / filename
            image = part.as_image()
            image.save(filepath)
            saved.append(filepath)
            img_idx += 1

    return saved


def register(subparsers):
    p = subparsers.add_parser("nanobanana", help="generate or edit images via Gemini")
    p.add_argument("prompt", help="text prompt for generation or editing")
    p.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="FILE",
        help="input image(s) for editing (repeatable)",
    )
    p.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        default="flash",
        help="model to use (default: flash)",
    )
    p.add_argument(
        "--aspect-ratio",
        choices=ASPECT_RATIOS,
        metavar="RATIO",
        help="output aspect ratio",
    )
    p.add_argument(
        "--size",
        choices=SIZES,
        metavar="SIZE",
        help="output resolution (pro model only): 1K, 2K, 4K",
    )
    p.add_argument(
        "--search", action="store_true", help="enable Google Search grounding"
    )
    p.add_argument(
        "--output-dir",
        default="./nanobanana-output",
        help="output directory (default: ./nanobanana-output)",
    )
    p.set_defaults(func=run)


def run(args):
    if args.size and args.model != "pro":
        print("error: --size requires --model pro", file=sys.stderr)
        sys.exit(1)

    for p in args.image:
        if not os.path.isfile(p):
            print(f"error: image not found: {p}", file=sys.stderr)
            sys.exit(1)

    if not os.environ.get("GEMINI_API_KEY"):
        print("error: GEMINI_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    client = genai.Client()
    model = MODELS[args.model]
    contents = build_contents(args.prompt, args.image)
    config = build_config(args)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    saved = save_images(response, args.output_dir)

    if not saved:
        print("error: no images generated", file=sys.stderr)
        sys.exit(1)

    for path in saved:
        print(path)
