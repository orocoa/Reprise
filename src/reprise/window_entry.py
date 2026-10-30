"""Isolated source-window bridge; needs host Python/Git, no desktop runtime bundle."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reprise.launcher import open_workbench, open_repository, shutdown


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('open', 'shutdown'))
    parser.add_argument('--data', required=True)
    parser.add_argument('--lang', choices=('zh', 'en'), default='en')
    parser.add_argument('--instance-id')
    parser.add_argument('--project', help='Exact registered project selected by the invoking task')
    args = parser.parse_args(argv)
    if not args.data.strip():
        parser.error('--data requires a non-empty path')
    if args.command == 'shutdown' and not args.instance_id:
        parser.error('Window shutdown requires --instance-id')
    try:
        if args.command == 'open':
            result = (open_repository(args.data, args.project, browser=False, language=args.lang)
                      if args.project else open_workbench(args.data, browser=False, language=args.lang))
        else:
            result = shutdown(args.data, instance_id=args.instance_id)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print('Reprise window: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
