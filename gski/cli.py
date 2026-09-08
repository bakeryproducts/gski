import argparse
import sys

import argcomplete
import httpx
from google.genai import errors as genai_errors
import openai


def _format_genai_error(e: genai_errors.APIError) -> str:
    status = getattr(e, "status", None)
    code = getattr(e, "code", None)
    msg = getattr(e, "message", None)
    prefix = " ".join(str(p) for p in [code, status] if p)
    if prefix and msg:
        return f"{prefix}: {msg}"
    return prefix or msg or str(e)


def _format_openai_error(e: openai.OpenAIError) -> str:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    msg = getattr(e, "message", None) or str(e)
    if code and str(code) not in str(msg):
        return f"{code}: {msg}"
    return str(msg)


def main():
    parser = argparse.ArgumentParser(prog="gski")
    sub = parser.add_subparsers(dest="command")

    from gski.audioscope import register as as_register
    from gski.deepresearch import register as dr_register
    from gski.gptimage2 import register as gi_register
    from gski.llm_process import register as lp_register
    from gski.nanobanana import register as nb_register
    from gski.nanoscope import register as ns_register
    from gski.omni import register as omni_register
    from gski.setup import register as setup_register
    from gski.tgscope import register as tg_register
    from gski.voiceover import register as vo_register
    from gski.websearch import register as ws_register
    from gski.solver import register as sv_register
    from gski.youtube_scope import register as ys_register

    as_register(sub)
    dr_register(sub)
    gi_register(sub)
    lp_register(sub)
    nb_register(sub)
    ns_register(sub)
    omni_register(sub)
    setup_register(sub)
    tg_register(sub)
    vo_register(sub)
    sv_register(sub)
    ws_register(sub)
    ys_register(sub)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except genai_errors.APIError as e:
        print(f"error: {_format_genai_error(e)}", file=sys.stderr)
        sys.exit(1)
    except openai.OpenAIError as e:
        print(f"error: {_format_openai_error(e)}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
