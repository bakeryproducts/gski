import argparse
import sys

import argcomplete


def main():
    parser = argparse.ArgumentParser(prog="gski")
    sub = parser.add_subparsers(dest="command")

    from gski.nanobanana import register as nb_register
    from gski.nanoscope import register as ns_register
    from gski.setup import register as setup_register

    nb_register(sub)
    ns_register(sub)
    setup_register(sub)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
