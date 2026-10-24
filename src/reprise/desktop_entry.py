"""Trusted bundle entry for the desktop window and the reusable CLI."""
import argparse
import json
import os
from pathlib import Path
import sys


# The app invokes this absolute script with -I -S, without cwd imports.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reprise import desktop_bundle
from reprise.cli import default_directory, main as cli_main
from reprise.launcher import open_workbench, shutdown, verified_server


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    forwarded = []
    if '--' in arguments:
        separator = arguments.index('--')
        forwarded = arguments[separator + 1:]
        arguments = arguments[:separator]
    parser = argparse.ArgumentParser(description='Reprise bundled runtime bridge')
    parser.add_argument('command', choices=('open', 'shutdown', 'doctor', 'cli', 'connect-skill'))
    parser.add_argument('--resources', required=True)
    parser.add_argument('--data')
    parser.add_argument('--instance-id')
    parser.add_argument('--to')
    parser.add_argument('--zip', dest='skill_zip')
    args = parser.parse_args(arguments)
    if forwarded and args.command != 'cli':
        parser.error('Only cli accepts arguments after --')
    if args.command == 'cli' and any(value is not None for value in
                                   (args.data, args.instance_id, args.to, args.skill_zip)):
        parser.error('Pass CLI options after --')
    if args.command == 'connect-skill' and not args.to:
        parser.error('connect-skill requires --to for the new Skill directory')
    if args.to is not None and args.command != 'connect-skill':
        parser.error('--to is only valid with connect-skill')
    if args.skill_zip is not None and args.command != 'connect-skill':
        parser.error('--zip is only valid with connect-skill')
    try:
        env = desktop_bundle.configure(args.resources)
        if args.command == 'doctor':
            result = desktop_bundle.doctor(args.resources)
        elif args.command == 'connect-skill':
            result = desktop_bundle.connect_skill(args.resources, args.to, archive=args.skill_zip)
        else:
            # Only this dedicated bridge process adopts the private environment.
            # configure itself remains pure and does not change global settings.
            os.environ.clear()
            os.environ.update(env)
            if args.command == 'cli':
                # Keep command parsing, output, and exit codes in the existing
                # CLI. In particular, do not wrap its JSON in another response.
                return cli_main(forwarded)
            directory = args.data if args.data is not None else default_directory()
            if not directory.strip():
                raise ValueError('Data directory must not be empty')
            if args.command == 'open':
                result = open_workbench(directory, browser=False)
                record = verified_server(directory)
                if (not record or record['pid'] != result['pid'] or
                        record['instance_id'] != result.get('instance_id')):
                    raise ValueError('Opened service changed before ownership was confirmed')
                result['instance_id'] = record['instance_id']
            else:
                if not args.instance_id:
                    raise ValueError('Desktop shutdown requires --instance-id')
                result = shutdown(directory, instance_id=args.instance_id)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print('Reprise desktop: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
