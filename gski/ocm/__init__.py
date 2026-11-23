from gski.ocm.cmds import cmd_abort, cmd_ls, cmd_mark, cmd_send, cmd_show, cmd_start


def register(subparsers):
    p = subparsers.add_parser("ocm", help="manage opencode orchestrator streams")
    sub = p.add_subparsers(dest="ocm_cmd", required=True)

    s = sub.add_parser("start", help="start an orchestrator stream; notifies automatically when reported")
    s.add_argument("name")
    s.add_argument("text", help="high-level task for the orchestrator")
    s.add_argument("--dir", help="working directory for the orchestrator (default: cwd)")
    s.add_argument("--model", help="provider/model")
    s.add_argument("--allow", action="append", help="extra allow rule, e.g. 'shell:git *' or 'shell:ssh *'")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("ls", help="list orchestrator streams and their ocq runs")
    s.add_argument("--status", nargs="+")
    s.add_argument("--all", action="store_true", help="expand workers for finished streams too")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("show", help="show stream status, workers, and orchestrator's last reply")
    s.add_argument("name")
    s.add_argument("--chars", type=int, default=4000)
    s.add_argument("--full", action="store_true", help="include full task prompt, allow rules, session, and dir")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("send", help="message a stream (<name> <text>) or parent manager (.. <text>)")
    s.add_argument("name")
    s.add_argument("text")
    s.add_argument("--queue", action="store_true", help="deliver after the current turn instead of steering")
    s.add_argument("--allow", action="append", help="grant additional allow rule to the session")
    s.set_defaults(func=cmd_send)

    for name, status in (("done", "done"), ("fail", "failed")):
        s = sub.add_parser(name, help=f"mark stream {status}")
        s.add_argument("name")
        s.add_argument("--note")
        s.set_defaults(func=lambda a, st=status: cmd_mark(a, st))

    s = sub.add_parser("abort", help="abort running orchestrator stream(s) -> reported")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_abort)
