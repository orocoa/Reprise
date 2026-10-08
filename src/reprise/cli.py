"""CLI shares the same repository and orchestration services as the browser."""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def default_directory():
    if os.environ.get('REPRISE_DATA'):
        return os.environ['REPRISE_DATA']
    if sys.platform == 'darwin':
        return str(Path.home() / 'Library/Application Support/Reprise')
    return str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'reprise')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='reprise', description='Local Git history and reproducible preview evidence')
    parser.add_argument('--data', default=default_directory(), help='State and retained artifacts directory, outside source repositories')
    commands = parser.add_subparsers(dest='command', required=True)
    server = commands.add_parser('serve'); server.add_argument('--port', type=int, default=51582)
    register = commands.add_parser('import'); register.add_argument('path'); register.add_argument('--name')
    commands.add_parser('projects')
    for name in ('history', 'detect'):
        item = commands.add_parser(name); item.add_argument('path'); item.add_argument('--ref', default='--all' if name == 'history' else 'HEAD')
    history = commands.choices['history']; history.add_argument('--limit', type=int, default=50); history.add_argument('--offset', type=int, default=0)
    recipe = commands.add_parser('recipe'); recipe.add_argument('project'); recipe.add_argument('file', help='JSON recipe file; explicit configuration, commands execute only on run/capture')
    recipe.add_argument('--sha', default='HEAD', help='Commit whose recipe is saved (resolved to exact SHA)')
    cancel = commands.add_parser('cancel'); cancel.add_argument('job', help='Run/capture job ID to cancel')
    for name in ('run', 'capture'):
        item = commands.add_parser(name); item.add_argument('project'); item.add_argument('--sha', default='HEAD')
        if name == 'capture': item.add_argument('--base')
    commands.add_parser('runtimes')
    stop = commands.add_parser('stop'); stop.add_argument('runtime')
    manual = commands.add_parser('evidence'); manual.add_argument('project'); manual.add_argument('path'); manual.add_argument('--sha', default='HEAD'); manual.add_argument('--kind', choices=['image', 'video', 'file'], default='file'); manual.add_argument('--title')
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            from .server import serve
            serve(args.data, args.port)
            return 0
        if args.command in ('history', 'detect'):
            from .git import Repository
            repository = Repository(args.path)
            if args.command == 'history':
                result = repository.history(args.ref, args.limit, args.offset)
            else:
                from .detection import detect
                result = detect(repository, args.ref)
        elif args.command in ('import', 'projects', 'recipe'):
            from .projects import ProjectStore
            projects = ProjectStore(args.data)
            if args.command == 'import': result = projects.add(args.path, args.name)
            elif args.command == 'projects': result = projects.list()
            else: result = projects.save_recipe(args.project, json.loads(Path(args.file).read_text()), args.sha)
        else:
            from .service import Reprise
            app = Reprise(args.data)
            try:
                if args.command == 'runtimes': result = app.runtimes.list()
                elif args.command == 'cancel': result = app.jobs.cancel(args.job)
                elif args.command == 'stop': result = app.runtimes.stop(args.runtime)
                elif args.command == 'evidence': result = app.evidence.manual(app.projects.repository(args.project), args.project, vars(args))
                else:
                    job = app.execute(args.project, args.command, vars(args))
                    try:
                        while job['status'] in ('queued', 'running', 'cancelling'):
                            time.sleep(.1)
                            job = app.jobs.get(job['id'])
                    except KeyboardInterrupt:
                        app.jobs.cancel(job['id'])
                        while job['status'] in ('queued', 'running', 'cancelling'):
                            time.sleep(.1)
                            job = app.jobs.get(job['id'])
                    result = job
            finally:
                app.close()
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return (130 if result.get('status') == 'cancelled' else 1 if result.get('status') == 'failed' else 0) if isinstance(result, dict) else 0
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
