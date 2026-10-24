#!/usr/bin/env python3
"""Open the source package's empty workbench without importing the current folder."""
import argparse
import json
from pathlib import Path
import shutil
import sys


def main(argv=None):
    if sys.version_info < (3, 9):
        print('Reprise 需要 Python 3.9 或更新版本。 / Reprise requires Python 3.9 or newer.', file=sys.stderr)
        return 1
    source = Path(__file__).resolve().parents[1] / 'src'
    if not (source / 'reprise' / 'launcher.py').is_file():
        print('未找到完整的 Reprise 程序。请保留解压后的整个目录，再打开 Reprise.command。 / Keep the complete extracted Reprise folder.', file=sys.stderr)
        return 1
    sys.path.insert(0, str(source))
    try:
        from reprise.cli import default_directory, port_number
        from reprise.launcher import open_workbench
    except ImportError as error:
        print('Reprise 无法读取程序文件，请检查完整安装。 / Could not load Reprise: ' + str(error), file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description='Open Reprise and choose a local project in the browser.')
    parser.add_argument('--data', default=default_directory(), help='Optional existing Reprise data location')
    parser.add_argument('--port', type=port_number, default=0)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--lang', choices=('zh', 'en'))
    parser.add_argument('--json', action='store_true', help='Print a machine-readable launch result')
    args = parser.parse_args(argv)
    if not shutil.which('git'):
        print('Reprise 需要本机 Git。请先安装 Git，再打开工作台。 / Install Git before opening Reprise.', file=sys.stderr)
        return 1
    try:
        result = open_workbench(args.data, args.port, not args.no_browser, args.lang)
    except (OSError, ValueError, RuntimeError) as error:
        print('Reprise 未能打开。 / Reprise could not open: ' + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print('Reprise 工作台已准备好，请在浏览器里选择本地项目文件夹。')
        print('Reprise is ready. Choose a local project folder in the browser.')
        print(result['url'])
        print('结束使用可在工作台中停止服务。 / Stop the service from the workbench when finished.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
