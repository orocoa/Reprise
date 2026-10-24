#!/bin/sh
# Create an uploadable thin Skill connected to this complete runtime folder.
# The runtime stays in place; no client settings or existing Skills are changed.
set -eu
ROOT=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")" && /bin/pwd -P)
if [ "$#" -gt 1 ]; then
    echo '用法：Prepare Skill.command [输出文件夹] / Usage: Prepare Skill.command [output folder]' >&2
    exit 1
fi
output_parent=${1:-"$HOME/Downloads"}
if ! output_parent=$(CDPATH= cd -- "$output_parent" && /bin/pwd -P); then
    echo '请选择一个已经存在的输出文件夹。 / Choose an existing output folder.' >&2
    exit 1
fi
case "$output_parent/" in
    "$ROOT/"*)
        echo 'Skill 输出必须放在完整运行包以外。 / Keep the Skill output outside the complete runtime folder.' >&2
        exit 1 ;;
esac
output_folder="$output_parent/Reprise Skill $(/bin/date -u +%Y%m%d-%H%M%S)-$$"
/bin/mkdir -- "$output_folder"
"$ROOT/reprise" connect-skill --to "$output_folder/reprise" --zip "$output_folder/Reprise-skill.zip"
printf '\n%s\n%s\n\n%s\n' \
    '已生成可上传的 Reprise Skill。请在当前客户端的本地技能导入中选择下面的 ZIP。' \
    'Connected Reprise Skill ready. Import the ZIP below using your client’s local Skill importer.' \
    "$output_folder/Reprise-skill.zip"
printf '%s\n%s\n' \
    '请把当前完整运行包留在这个位置；此 ZIP 连接的是这台 Mac 上的运行包。' \
    'Keep this complete runtime folder in place. This ZIP connects to its current location on this Mac.'
# Finder is a convenience for a person double-clicking in Terminal. Piped CLI
# tests and agents only receive the path; no native UI is opened for them.
if [ -t 1 ]; then
    /usr/bin/open -R "$output_folder/Reprise-skill.zip" || true
fi
