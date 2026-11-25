# -*- coding: utf-8 -*-
"""Shared command-line bootstrap for the vim-notebox Python scripts.

Every entry script imports this module before any third-party or project
import and calls ``init()``::

    import _cli
    _cli.init()

It does three things:

1. Puts the scripts directory (symlinked *directories* resolved via
   ``realpath``) first on ``sys.path`` so the local modules (``notebox``,
   ``cnlook``, ``getTbupPdf``) are importable regardless of cwd.
2. Parses and strips ``--box DIR`` / ``--box=DIR`` / ``--notes-dir ...`` from
   ``sys.argv``.  When a box is given it is exported as ``NOTES_DIR``, which is
   what :mod:`notebox` and the generators read.  Precedence:

       --box DIR  >  $NOTES_DIR  >  current working directory

   Without ``--box`` the environment is left untouched, so the existing
   ``$NOTES_DIR`` / cwd fallbacks keep working exactly as before.
3. Handles ``-h`` / ``--help`` by printing the entry script's own module
   docstring (the per-script usage reference) and exiting 0.  Scripts that
   already use :mod:`argparse` call ``init(help=False)`` so argparse keeps
   ownership of the help output.

Set ``NOTES_NO_HELP=1`` to disable the help interception.
"""

import os
import sys


BOX_OPTIONS = ("--box", "--notes-dir")


def _strip_box(args):
    """Remove box options from *args*; return (remaining_args, box or None)."""
    rest = []
    box = None
    i = 0
    while i < len(args):
        arg = args[i]
        matched = False
        for opt in BOX_OPTIONS:
            if arg == opt:
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    print(f"HATA {opt} bir dizin gerektirir", file=sys.stderr)
                    raise SystemExit(2)
                box = args[i + 1]
                i += 2
                matched = True
                break
            if arg.startswith(opt + "="):
                box = arg.split("=", 1)[1]
                if not box:
                    print(f"HATA {opt} bir dizin gerektirir", file=sys.stderr)
                    raise SystemExit(2)
                i += 1
                matched = True
                break
        if matched:
            continue
        rest.append(arg)
        i += 1
    return rest, box


def _print_help():
    main = sys.modules.get("__main__")
    doc = (getattr(main, "__doc__", "") or "").strip()
    if doc:
        print(doc)
    else:
        print(f"Kullanım: {os.path.basename(sys.argv[0])} <ülke> [--box DIR]")
    print()
    print("Seçenekler:")
    print("  --box DIR, --notes-dir DIR   not kutusu (varsayılan: $NOTES_DIR veya cwd)")
    print("  -h, --help                   bu yardımı göster")
    print("  --box=DIR                    --box DIR ile aynı")


def init(help=True):
    """Bootstrap the interpreter for a directly executed script."""
    here = os.path.dirname(os.path.realpath(__file__))
    if not sys.path or sys.path[0] != here:
        sys.path.insert(0, here)

    args, box = _strip_box(sys.argv[1:])
    sys.argv = [sys.argv[0]] + args

    if box is not None:
        box = os.path.abspath(os.path.expanduser(box))
        os.environ["NOTES_DIR"] = box

    if (help and os.environ.get("NOTES_NO_HELP", "") != "1"
            and any(a in ("-h", "--help") for a in args)):
        _print_help()
        raise SystemExit(0)

    return os.environ.get("NOTES_DIR") or os.getcwd()
