from gski.oc_lib.api import DEFAULT_PORT
from gski.ocq.cmds import cmd_abort, cmd_ls, cmd_send, cmd_serve, cmd_show, cmd_spawn


def register(subparsers):
    p = subparsers.add_parser("ocq", help="orchestrate opencode worker sessions")
    sub = p.add_subparsers(dest="ocq_cmd", required=True)

    s = sub.add_parser("spawn", help="start worker task(s) in parallel; notifies automatically on completion")
    s.add_argument("run")
    s.add_argument("text", nargs="*", help="task text, one worker per argument")
    s.add_argument("--file", help="jsonl ({task, id?, agent?, model?, allow?}) or plain lines; - for stdin")
    s.add_argument("--agent", help="worker (default) or builder")
    s.add_argument("--model", help="provider/model")
    s.add_argument("--allow", action="append", help="extra allow rule, e.g. 'shell:ssh *'")
    s.set_defaults(func=cmd_spawn)

    s = sub.add_parser("ls", help="list runs, or tasks and results in <run>")
    s.add_argument("run", nargs="?")
    s.add_argument("--status", nargs="+")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("show", help="show task details, result, and worker's last reply")
    s.add_argument("run")
    s.add_argument("id")
    s.add_argument("--chars", type=int, default=4000)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("send", help="message/reopen a worker (<run> <id> <text>) or parent orchestrator (.. <text>)")
    s.add_argument("first", metavar="RUN_OR_PARENT", help="<run> or ..")
    s.add_argument("second", metavar="ID_OR_TEXT", help="<id> or <text>")
    s.add_argument("third", nargs="?", metavar="TEXT", help="<text> when sending to <run> <id>")
    s.add_argument("--queue", action="store_true", help="deliver after current turn instead of steering")
    s.add_argument("--allow", action="append", help="grant additional allow rule to the worker session")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("abort", help="abort running worker(s) (all if no ids) -> failed")
    s.add_argument("run")
    s.add_argument("ids", nargs="*")
    s.set_defaults(func=cmd_abort)

    s = sub.add_parser("serve", help="optional: run a standalone opencode server")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.set_defaults(func=cmd_serve)
