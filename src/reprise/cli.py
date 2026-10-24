"""CLI shares the same repository and orchestration services as the browser."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import time
from .processes import ProcessCleanupError


def default_directory():
    if os.environ.get('REPRISE_DATA'):
        return os.environ['REPRISE_DATA']
    if sys.platform == 'darwin':
        return str(Path.home() / 'Library/Application Support/Reprise')
    return str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'reprise')


def port_number(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('port must be an integer') from None
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError('port must be between 0 and 65535')
    return number


def wait_job(app, job):
    try:
        while job['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.1)
            job = app.jobs.get(job['id'])
    except KeyboardInterrupt:
        app.jobs.cancel(job['id'])
        while job['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.1)
            job = app.jobs.get(job['id'])
    return job


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Accept the installed Skill's --data placement while keeping one CLI/core.
    data_args, remainder = [], []
    i = 0
    while i < len(argv):
        if argv[i] == '--data' and i + 1 < len(argv):
            data_args = argv[i:i + 2]; i += 2
        elif argv[i].startswith('--data='):
            data_args = [argv[i]]; i += 1
        else:
            remainder.append(argv[i]); i += 1
    argv = data_args + remainder
    if '--workbench' in remainder and any(
            argument.split('=', 1)[0] in ('--repo', '--project', '--registry')
            for argument in remainder):
        argparse.ArgumentParser(prog='reprise').error(
            '--workbench cannot be combined with --repo, --project or --registry')
    if '--repo' in remainder or '--project' in remainder or '--registry' in remainder:
        from . import compat
        from .projects import ProjectStore
        data = (data_args[1] if len(data_args) == 2 else data_args[0].split('=', 1)[1]) if data_args else default_directory()
        if '--project' in remainder and '--registry' not in remainder:
            flag = remainder.index('--project')
            try:
                store = ProjectStore(data)
                identifier = store.identify(remainder[flag + 1])
                native = store.record(identifier).get('kind') != 'archive'
            except (KeyError, IndexError):
                native = False
            except ValueError as error:
                print(str(error), file=sys.stderr); return 1
            if native:
                record = store.record(identifier)
                if remainder[0] == 'bundle' and record.get('kind') == 'folder':
                    print('普通文件夹请使用 export 导出；不会从所在的其他 Git 仓库生成 bundle。', file=sys.stderr)
                    return 1
                if remainder[0] in ('refs', 'compare', 'bundle') and record.get('kind') != 'folder':
                    remainder[flag:flag + 2] = ['--repo', record['path']]
                    return compat.main(data_args + remainder)
                remainder[flag:flag + 2] = [identifier]
                if remainder[0] == 'open' and record.get('kind') == 'folder':
                    remainder.append('--folder')
                if remainder[0] in ('restore', 'export'):
                    remainder = ['--sha' if a == '--ref' else a for a in remainder]
                argv = data_args + remainder
            else:
                if remainder[0] in ('relink', 'migrate'):
                    print('旧归档保留原名称适配器；请先恢复到新目录，不直接改写归档来源。', file=sys.stderr)
                    return 1
                try:
                    return compat.main(argv)
                except (ValueError, OSError, KeyError) as error:
                    print(str(error), file=sys.stderr); return 1
        else:
            try:
                return compat.main(argv)
            except (ValueError, OSError, KeyError) as error:
                print(str(error), file=sys.stderr); return 1
    known = {'open', 'serve', 'shutdown', 'import', 'import-folders', 'folder-import-report', 'projects', 'history', 'detect', 'recipe', 'cancel', 'run', 'capture', 'restore', 'export', 'runtimes', 'stop', 'evidence', 'snapshot', 'save', 'preview-preferences', 'privacy', 'organize', 'review', 'select', 'refs', 'compare', 'verify', 'storage', 'backup', 'backup-check', 'data-restore', 'relink', 'migrate', 'version-delete-plan', 'version-estimate', 'version-delete', 'environments', 'environment-check', 'environment-release'}
    position = 0
    while position < len(argv) and (argv[position] == '--data' or argv[position].startswith('--data=')):
        if argv[position] == '--data' and position + 1 >= len(argv):
            break  # argparse reports the missing value, without indexing past argv
        position += 1 if '=' in argv[position] else 2
    if position == len(argv):
        argv[position:] = ['open', '--workbench']
    elif argv[position] not in known and not argv[position].startswith('-'):
        argv.insert(position, 'open')
    parser = argparse.ArgumentParser(prog='reprise', description='Local content versions, Git history and verified recovery')
    parser.add_argument('--data', default=default_directory(), help='State and retained artifacts directory, outside source repositories')
    commands = parser.add_subparsers(dest='command', required=True)
    server = commands.add_parser('serve'); server.add_argument('--port', type=port_number, default=51582)
    server.add_argument('--fallback-port', action='store_true', help=argparse.SUPPRESS)
    opening = commands.add_parser('open'); opening.add_argument('path', nargs='?', help='Explicit folder or Git repository path; omit to open the workspace without importing a directory')
    opening.add_argument('--workbench', action='store_true', help='Open the workspace without importing the current directory')
    opening.add_argument('--port', type=port_number, default=0); opening.add_argument('--no-browser', action='store_true')
    opening.add_argument('--lang', choices=('zh', 'en'))
    opening.add_argument('--folder', action='store_true', help='Manage this folder as content, including folders inside a Git project')
    opening.add_argument('--history', action='append', default=[], help='Explicit related read-only Git archive')
    opening.add_argument('--history-catalog', help='Saved version catalog, excluding archive metadata commits')
    commands.add_parser('shutdown')
    register = commands.add_parser('import'); register.add_argument('path'); register.add_argument('--name')
    register.add_argument('--folder', action='store_true')
    register.add_argument('--exclude', action='append', default=None)
    collection = commands.add_parser('import-folders', help='Save explicitly ordered folders / ZIP contents as one new project, restore and assess; never delete')
    collection.add_argument('--manifest', required=True)
    collection.add_argument('--check', action='store_true', help='Read-only metadata/cost preview; no snapshots or recovery copies')
    collection.add_argument('--preflight', help='Previously reviewed fingerprint; changed inputs require another preview')
    collection_report = commands.add_parser('folder-import-report', help='Read or refresh a retained original-folder removal assessment')
    collection_report.add_argument('report'); collection_report.add_argument('--refresh', action='store_true')
    snapshot = commands.add_parser('snapshot'); snapshot.add_argument('project'); snapshot.add_argument('--title', default='')
    saving = commands.add_parser('save'); saving.add_argument('path'); saving.add_argument('--title', default=''); saving.add_argument('--name'); saving.add_argument('--exclude', action='append', default=None)
    for saving_command in (snapshot, saving):
        preview_choice = saving_command.add_mutually_exclusive_group()
        preview_choice.add_argument('--preview', choices=('none', 'manual', 'remind', 'auto'), help='Remember screenshot preference for this project; auto needs an explicitly saved recipe')
        preview_choice.add_argument('--capture-static', action='store_true', help='After saving, try a local static website capture for this draft without changing the project screenshot preference')
        saving_command.add_argument('--preview-recipe-sha', help='Saved recipe revision explicitly approved for reuse after future saves')
    preview = commands.add_parser('preview-preferences', help='Inspect or explicitly set a project screenshot preference')
    preview.add_argument('project'); preview.add_argument('--mode', choices=('none', 'manual', 'remind', 'auto'))
    preview.add_argument('--recipe-sha')
    listing = commands.add_parser('projects'); listing.add_argument('--details', action='store_true')
    commands.add_parser('privacy')
    commands.add_parser('storage', help='Inspect only this data directory; no file contents or cleanup')
    backup = commands.add_parser('backup', help='Create a verified managed-data backup while this data directory is offline')
    backup.add_argument('--to', required=True)
    backup_check = commands.add_parser('backup-check', help='Read back and verify a completed managed-data backup')
    backup_check.add_argument('backup')
    data_restore = commands.add_parser('data-restore', help='Restore a managed-data backup into a new data directory')
    data_restore.add_argument('backup'); data_restore.add_argument('--to', required=True)
    for operation in ('relink', 'migrate'):
        item = commands.add_parser(operation)
        item.add_argument('project'); item.add_argument('--to', required=True)
        if operation == 'relink': item.add_argument('--check', action='store_true', help='Inspect identity without changing the registration')
    verification = commands.add_parser('verify', help='Read and check one saved folder version, without restoring it')
    verification.add_argument('project'); verification.add_argument('--sha', '--ref', default='HEAD')
    organizing = commands.add_parser('organize'); organizing.add_argument('project'); organizing.add_argument('--sha', default='HEAD')
    organizing.add_argument('--check', action='store_true', help='Preview snapshot duplicate bytes and restore cost; no recovery copy or selection')
    review = commands.add_parser('review'); review.add_argument('plan'); review.add_argument('--details', action='store_true')
    selection = commands.add_parser('select'); selection.add_argument('plan'); selection.add_argument('--path', action='append', dest='paths', default=[])
    references = commands.add_parser('refs'); references.add_argument('project')
    comparison = commands.add_parser('compare'); comparison.add_argument('project'); comparison.add_argument('--base', required=True); comparison.add_argument('--target', required=True)
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
    deletion_plan = commands.add_parser('version-delete-plan', help='Explain selected managed snapshot deletion and joint unique bytes')
    deletion_plan.add_argument('project'); deletion_plan.add_argument('--sha', dest='shas', action='append', required=True)
    estimation = commands.add_parser('version-estimate', help='Measure a fresh deletion plan by streaming packs; no versions removed')
    estimation.add_argument('project'); estimation.add_argument('--plan', dest='plan_id', required=True)
    deletion = commands.add_parser('version-delete', help='Delete only snapshots in a fresh reviewed plan and verify all retained content')
    deletion.add_argument('project'); deletion.add_argument('--plan', dest='plan_id', required=True); deletion.add_argument('--confirm', action='store_true')
    environments = commands.add_parser('environments'); environments.add_argument('project'); environments.add_argument('--sha')
    for name in ('environment-check', 'environment-release'):
        item = commands.add_parser(name); item.add_argument('environment')
        if name == 'environment-release': item.add_argument('--confirm', action='store_true')
    for name in ('restore', 'export'):
        item = commands.add_parser(name)
        item.add_argument('project', help='Registered project ID')
        item.add_argument('--sha', default='HEAD')
        item.add_argument('--to', required=True, help='New directory (restore) or new ZIP file (export); never overwritten')
        item.add_argument('--path', dest='paths', action='append', help='Recover only this relative file/directory; repeat to select more')
    stop = commands.add_parser('stop'); stop.add_argument('runtime')
    manual = commands.add_parser('evidence'); manual.add_argument('project'); manual.add_argument('path'); manual.add_argument('--sha', default='HEAD'); manual.add_argument('--kind', choices=['image', 'video', 'file'], default='file'); manual.add_argument('--title')
    args = parser.parse_args(argv)
    if getattr(args, 'preview_recipe_sha', None) and args.preview != 'auto':
        parser.error('--preview-recipe-sha requires --preview auto')
    if args.command == 'open' and args.workbench and (
            args.path is not None or args.folder or args.history or args.history_catalog is not None):
        parser.error('--workbench cannot be combined with a path, --folder, --history or --history-catalog')
    if args.command == 'open' and args.path is None and (
            args.folder or args.history or args.history_catalog is not None):
        parser.error('--folder, --history and --history-catalog require an explicit project path')
    leases = contextlib.ExitStack()
    try:
        if args.command in ('backup', 'backup-check', 'data-restore'):
            from .backup import create_backup, verify_backup, restore_backup
            if args.command == 'backup': result = create_backup(args.data, args.to)
            elif args.command == 'backup-check': result = verify_backup(args.backup)
            else: result = restore_backup(args.backup, args.to)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result.get('status') not in ('failed', 'incomplete', 'partial') else 1
        if args.command == 'storage':
            from .storage_report import storage_report
            result = storage_report(args.data)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result['status'] == 'complete' else 1
        if args.command in ('history', 'detect', 'refs', 'compare', 'projects'):
            # Folder reads may initialize the owned library or persist Git status.
            # Keep them out of an offline backup's exclusive consistency window.
            from .maintenance import DataLease
            directory = Path(args.data).expanduser().resolve()
            if directory.exists():
                leases.enter_context(DataLease(directory))
        if args.command == 'serve':
            from .server import serve
            serve(args.data, args.port, fallback_port=args.fallback_port)
            return 0
        if args.command in ('open', 'shutdown'):
            from .launcher import open_repository, open_workbench, shutdown
            if args.command == 'shutdown':
                result = shutdown(args.data)
            elif args.workbench or args.path is None:
                result = open_workbench(args.data, args.port, not args.no_browser, args.lang)
            else:
                result = open_repository(args.data, args.path,
                                         args.port, not args.no_browser, args.lang,
                                         args.history, args.history_catalog, 'folder' if args.folder else None)
        elif args.command in ('history', 'detect'):
            from .git import Repository
            from .projects import ProjectStore
            store = ProjectStore(args.data)
            try:
                repository = store.repository(store.identify(args.path))
            except KeyError:
                repository = Repository(args.path)
            if args.command == 'history':
                result = repository.history(args.ref, args.limit, args.offset)
            else:
                from .detection import detect
                result = detect(repository, args.ref)
        elif args.command in ('refs', 'compare'):
            from .projects import ProjectStore
            projects = ProjectStore(args.data)
            repository = projects.repository(projects.identify(args.project))
            result = ({'repository': repository.info(), 'refs': repository.refs()} if args.command == 'refs' else
                      {'repository': repository.info(), 'base': repository.resolve(args.base),
                       'target': repository.resolve(args.target), 'diff': repository.diff(args.target, args.base)})
        elif args.command in ('import', 'projects', 'recipe', 'preview-preferences'):
            from .projects import ProjectStore
            projects = ProjectStore(args.data)
            if args.command == 'import': result = projects.add(args.path, args.name, 'folder' if args.folder else None, args.exclude)
            elif args.command == 'projects': result = projects.list() if args.details else projects.summaries()
            elif args.command == 'preview-preferences':
                identifier = projects.identify(args.project)
                result = (projects.save_preview_preferences(identifier, args.mode, args.recipe_sha) if args.mode else
                          projects.record(identifier).get('preview_preferences', {'mode': 'remind', 'not_configured': True}))
            else: result = projects.save_recipe(args.project, json.loads(Path(args.file).read_text()), args.sha)
        else:
            from .service import Reprise
            app = Reprise(args.data)
            try:
                if args.command == 'privacy': result = app.privacy()
                elif args.command == 'review':
                    plan = app.organization.get(args.plan)
                    result = plan if args.details else app.organization.summary(plan)
                elif args.command == 'select': result = app.organization.select(args.plan, args.paths)
                elif args.command == 'runtimes': result = app.runtimes.list()
                elif args.command == 'cancel': result = app.jobs.cancel(args.job)
                elif args.command == 'stop': result = app.runtimes.stop(args.runtime)
                elif args.command == 'version-delete-plan':
                    result = app.version_delete_plan(app.projects.identify(args.project), args.shas)
                elif args.command == 'environments':
                    result = {'environments': app.runtimes.environments.list(app.projects.identify(args.project), args.sha)}
                elif args.command == 'environment-check': result = app.runtimes.environment_check(args.environment)
                elif args.command == 'environment-release':
                    if not args.confirm: raise ValueError('请明确确认释放此环境。')
                    result = app.runtimes.release_environment(args.environment)
                elif args.command == 'evidence': result = app.evidence.manual(app.projects.repository(args.project), args.project, vars(args))
                elif args.command == 'import-folders':
                    specification = json.loads(Path(args.manifest).read_text())
                    if args.preflight:
                        specification['preflight_fingerprint'] = args.preflight
                    result = (app.folder_imports.analyze(specification) if args.check else
                              wait_job(app, app.folder_imports.start(specification)))
                elif args.command == 'folder-import-report':
                    result = app.folder_imports.get(args.report)
                    if args.refresh:
                        result = wait_job(app, app.jobs.submit(result['project_id'], 'folder-import-review',
                            lambda cancel: app.folder_imports.review(args.report, cancel),
                            request={'report_id': args.report}, cancellable=True))
                else:
                    if args.command == 'relink' and args.check:
                        args.command = 'relink-check'
                    if args.command == 'organize' and args.check:
                        args.command = 'organize-check'
                    if args.command == 'save':
                        record = app.projects.add(args.path, args.name, 'folder', args.exclude)
                        args.project, args.command = record['id'], 'snapshot'
                    else:
                        args.project = app.projects.identify(args.project)
                    request = vars(args)
                    if args.command == 'snapshot' and args.preview:
                        request['preview_preferences'] = {'mode': args.preview, 'recipe_sha': args.preview_recipe_sha}
                    job = app.execute(args.project, args.command, request)
                    result = wait_job(app, job)
            finally:
                app.close()
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return (130 if result.get('status') == 'cancelled' else 1 if result.get('status') == 'failed' else 0) if isinstance(result, dict) else 0
    except KeyboardInterrupt:
        print('操作已中断；已生成的副本和诊断保留。', file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, ProcessCleanupError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        leases.close()
