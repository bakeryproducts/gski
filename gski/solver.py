"""Creative problem-solving toolkit: TRIZ, SCAMPER, Lateral Thinking, Six Hats, Morphological Analysis."""

import random
import sys

from gski.solver_data.triz import MATRIX, PARAMETERS, PRINCIPLES
from gski.solver_data.scamper import OPERATORS, ORDER as SCAMPER_ORDER
from gski.solver_data.lateral import MOVEMENT_TECHNIQUES, RANDOM_WORDS
from gski.solver_data.hats import HATS, HAT_ORDER, SEQUENCES


# -- TRIZ --


def run_triz_list(args):
    if args.list == "params":
        for pid, name in sorted(PARAMETERS.items()):
            print(f"  {pid:2d}. {name}")
    elif args.list == "principles":
        for pid, p in sorted(PRINCIPLES.items()):
            print(f"  {pid:2d}. {p['name']}")
            print(f"      {p['description']}")
    else:
        print(f"error: unknown list type: {args.list}", file=sys.stderr)
        sys.exit(1)


def run_triz_lookup(args):
    improve = args.improve
    worsen = args.worsen
    if improve not in PARAMETERS:
        print(
            f"error: unknown parameter {improve}. Use --list params.", file=sys.stderr
        )
        sys.exit(1)
    if worsen not in PARAMETERS:
        print(f"error: unknown parameter {worsen}. Use --list params.", file=sys.stderr)
        sys.exit(1)

    print(f"Contradiction: improve [{improve}] {PARAMETERS[improve]}")
    print(f"         while keeping [{worsen}] {PARAMETERS[worsen]}")
    print()

    key = (improve, worsen)
    if key not in MATRIX:
        print("No principles found in matrix for this pair.")
        print("Try reversing the parameters, or pick nearby parameters.")
        return

    principle_ids = MATRIX[key]
    print(f"Suggested principles ({len(principle_ids)}):")
    print()
    for pid in principle_ids:
        p = PRINCIPLES[pid]
        print(f"  [{pid}] {p['name']}")
        print(f"  {p['description']}")
        for sub in p["sub"]:
            print(f"    - {sub}")
        print()


def run_triz_random(args):
    n = args.count
    ids = random.sample(list(PRINCIPLES.keys()), min(n, len(PRINCIPLES)))
    print(f"Random TRIZ principles ({len(ids)}):")
    print()
    for pid in ids:
        p = PRINCIPLES[pid]
        print(f"  [{pid}] {p['name']}")
        print(f"  {p['description']}")
        for sub in p["sub"]:
            print(f"    - {sub}")
        print()


def run_triz(args):
    if args.list:
        run_triz_list(args)
    elif args.improve is not None and args.worsen is not None:
        run_triz_lookup(args)
    elif args.random:
        run_triz_random(args)
    else:
        print("error: use --list, --improve/--worsen, or --random", file=sys.stderr)
        sys.exit(1)


# -- SCAMPER --


def run_scamper(args):
    n = args.count
    if n >= len(SCAMPER_ORDER):
        selected = list(SCAMPER_ORDER)
    else:
        selected = random.sample(SCAMPER_ORDER, n)

    print(f"SCAMPER operators ({len(selected)}):")
    print()
    for key in selected:
        op = OPERATORS[key]
        print(f"  [{key}] {op['name']}")
        print(f"  {op['description']}")
        print()
        for q in op["questions"]:
            print(f"    ? {q}")
        print()


# -- Lateral Thinking --


def run_lateral(args):
    n = args.count
    words = random.sample(RANDOM_WORDS, min(n, len(RANDOM_WORDS)))
    technique = random.choice(MOVEMENT_TECHNIQUES)

    print(f"Random provocation words ({len(words)}):")
    for w in words:
        print(f"  * {w}")
    print()
    print(f"Movement technique: {technique['name']}")
    print(f"  {technique['instruction']}")
    print()
    print(f"  Example: {technique['example']}")
    print()
    print("Steps:")
    print("  1. Pick one word above")
    print("  2. List 5+ associations/properties of that word")
    print(
        "  3. Apply the movement technique to connect each association to your problem"
    )
    print("  4. Capture every idea, no matter how absurd")


# -- Six Thinking Hats --


def run_hats(args):
    if args.sequence:
        seq_name = args.sequence
        if seq_name not in SEQUENCES:
            print(f"error: unknown sequence '{seq_name}'", file=sys.stderr)
            print(f"available: {', '.join(SEQUENCES.keys())}", file=sys.stderr)
            sys.exit(1)
        seq = SEQUENCES[seq_name]
        hat_keys = seq["order"]
        print(f"Sequence: {seq['description']}")
    elif args.random:
        non_blue = [h for h in HAT_ORDER if h != "blue"]
        random.shuffle(non_blue)
        hat_keys = ["blue"] + non_blue + ["blue"]
        print("Sequence: random (blue bookends)")
    else:
        # default: random single hat
        hat_key = random.choice(HAT_ORDER)
        hat_keys = [hat_key]
        print("Random single hat:")

    print()
    for i, key in enumerate(hat_keys, 1):
        hat = HATS[key]
        print(f"  {i}. {hat['name']} — {hat['focus']}")
        print(f"     {hat['description']}")
        print()
        for q in hat["questions"]:
            print(f"     ? {q}")
        print()


# -- Morphological Analysis --


def run_morph(args):
    axes = args.axes
    if len(axes) < 2:
        print("error: need at least 2 axes", file=sys.stderr)
        sys.exit(1)

    n = args.count
    print(f"Morphological analysis — {len(axes)} axes, {n} random combinations:")
    print()
    print("Axes:")
    for i, axis in enumerate(axes, 1):
        print(f"  {i}. {axis}")
    print()

    print("Random combinations:")
    for i in range(n):
        combo = [random.choice(axes) for _ in range(2)]
        # pick 2 different axes to combine
        if len(axes) >= 2:
            pair = random.sample(range(len(axes)), 2)
            print(
                f"  {i + 1}. Combine axis {pair[0] + 1} ({axes[pair[0]]}) × axis {pair[1] + 1} ({axes[pair[1]]})"
            )
        print()

    print("Instructions:")
    print("  1. For each axis above, brainstorm 3-5 possible values/options")
    print("  2. The random pairings above suggest which axes to cross-pollinate first")
    print(
        "  3. For each pairing, pick one value from each axis and imagine the combination"
    )
    print("  4. Evaluate which combinations reveal non-obvious solutions")


# -- CLI registration --


def register(subparsers):
    p = subparsers.add_parser("solver", help="creative problem-solving toolkit")
    sub = p.add_subparsers(dest="mode")

    # triz
    triz = sub.add_parser("triz", help="TRIZ contradiction matrix and principles")
    triz.add_argument(
        "--list",
        "-l",
        choices=["params", "principles"],
        help="list parameters or principles",
    )
    triz.add_argument("--improve", "-i", type=int, help="parameter ID to improve")
    triz.add_argument("--worsen", "-w", type=int, help="parameter ID that worsens")
    triz.add_argument(
        "--random", "-r", action="store_true", help="pick random principles"
    )
    triz.add_argument(
        "--count",
        "-n",
        type=int,
        default=3,
        help="number of random principles (default: 3)",
    )
    triz.set_defaults(func=run_triz)

    # scamper
    scamper = sub.add_parser("scamper", help="SCAMPER creative operators")
    scamper.add_argument(
        "--count",
        "-n",
        type=int,
        default=2,
        help="number of random operators (default: 2)",
    )
    scamper.set_defaults(func=run_scamper)

    # lateral
    lateral = sub.add_parser("lateral", help="lateral thinking random provocation")
    lateral.add_argument(
        "--count", "-n", type=int, default=3, help="number of random words (default: 3)"
    )
    lateral.set_defaults(func=run_lateral)

    # hats
    hats = sub.add_parser("hats", help="Six Thinking Hats")
    hats.add_argument(
        "--sequence", "-s", choices=list(SEQUENCES.keys()), help="use a named sequence"
    )
    hats.add_argument(
        "--random",
        "-r",
        action="store_true",
        help="random hat sequence (blue bookends)",
    )
    hats.add_argument(
        "--count", "-n", type=int, default=1, help="unused, for consistency"
    )
    hats.set_defaults(func=run_hats)

    # morph
    morph = sub.add_parser("morph", help="morphological analysis")
    morph.add_argument("axes", nargs="+", help="axes/dimensions to combine")
    morph.add_argument(
        "--count",
        "-n",
        type=int,
        default=3,
        help="number of random combinations (default: 3)",
    )
    morph.set_defaults(func=run_morph)

    p.set_defaults(
        func=lambda args: p.print_help() if not args.mode else args.func(args)
    )


def run(args):
    if not args.mode:
        print(
            "error: choose a mode: triz, scamper, lateral, hats, morph", file=sys.stderr
        )
        sys.exit(1)
    args.func(args)
