"""Start the window, or the command line when there are options."""

import os
import sys


def wants_cli(argv):
    if os.path.splitext(os.path.basename(sys.argv[0]))[0].lower().endswith("-cli"):
        return True
    return any(a.startswith("-") for a in argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # the Windows window program has no console: printing goes nowhere instead of failing
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    if argv and argv[0] == "--cli":
        argv = argv[1:]
        cli = True
    else:
        cli = wants_cli(argv)
    if argv[:1] == ["--selftest"]:
        from kanzonassvg import selftest

        return selftest.run(argv[1:])
    if cli:
        from kanzonassvg import cli as cli_module

        return cli_module.run(argv)
    from kanzonassvg import app

    return app.run(argv)
