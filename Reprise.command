#!/bin/sh
# Open the workbench from this package, without importing Terminal's directory.
reprise_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd) || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Reprise 需要 Python 3.9 或更新版本。请先安装，再双击此文件。' \
        'Reprise requires Python 3.9 or newer. Install Python, then open this file again.'
    if [ -t 0 ]; then
        printf '%s' '按回车关闭 / Press Return to close: '
        read -r reprise_reply
    fi
    exit 1
fi
python3 -I -S "$reprise_dir/scripts/start_workbench.py" "$@"
reprise_status=$?
if [ "$reprise_status" -ne 0 ] && [ -t 0 ]; then
    printf '%s' '按回车关闭 / Press Return to close: '
    read -r reprise_reply
fi
exit "$reprise_status"
