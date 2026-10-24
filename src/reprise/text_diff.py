"""Bounded line comparisons using Python's standard-library difflib.

SequenceMatcher/get_grouped_opcodes are imported, not copied or reimplemented.
API and license: https://docs.python.org/3.9/library/difflib.html
https://docs.python.org/3/license.html (PSF License Version 2).
"""
from collections import Counter
from difflib import SequenceMatcher


MAX_INPUT_BYTES = 65536
MAX_LINES = 4000
MAX_LINE_CHARS = 8192
MAX_LINE_PAIRS = 4000000
MAX_MATCH_CANDIDATES = 250000
MAX_OUTPUT_ROWS = 2000


def _line(value):
    for suffix, name in (('\r\n', 'crlf'), ('\n', 'lf'), ('\r', 'cr')):
        if value.endswith(suffix):
            return value[:-len(suffix)], name
    return value, 'none'


def _row(kind, value, before, after, change=None):
    text, eol = _line(value)
    return {'kind': kind, 'before_line': before, 'after_line': after,
            'text': text, 'eol': eol, 'change': change}


def build_text_diff(pair, context=3):
    """Return JSON-ready hunks from workspace.file_comparison's before/after.

    Missing/binary/error/truncated sides are never treated as empty text. An
    explicit ``absent`` side *is* empty. Line numbers are one-based, null on the
    absent side of a row. ``summary`` counts the complete comparison; rendered
    rows and unchanged gap rows share a hard output budget. Context is 0..10.
    No repository, filesystem, subprocess, HTML, or runtime mutations occur.
    """
    context = min(10, max(0, context)) if type(context) is int else 3
    result = {'schema': 1, 'status': 'unavailable', 'reason': None,
              'context': context, 'hunks': [], 'gaps': [],
              'summary': {'inserted': 0, 'deleted': 0, 'changes': 0,
                          'before_lines': None, 'after_lines': None,
                          'shown_changes': 0, 'shown_rows': 0,
                          'omitted_rows': 0},
              'sides': {}, 'limits': {'input_bytes_per_side': MAX_INPUT_BYTES,
                                      'lines_per_side': MAX_LINES,
                                      'line_characters': MAX_LINE_CHARS,
                                      'output_rows': MAX_OUTPUT_ROWS}}
    if not isinstance(pair, dict):
        result['reason'] = 'invalid_input'
        return result
    texts = []
    for name in ('before', 'after'):
        side = pair.get(name)
        if not isinstance(side, dict):
            result['reason'] = 'missing_side'
            return result
        result['sides'][name] = {'absent': side.get('absent') is True}
        if side.get('binary'):
            result.update(reason='binary')
            return result
        if side.get('truncated'):
            result.update(status='truncated', reason='input_truncated')
            return result
        if side.get('too_large'):
            result.update(status='too_large', reason='input_bytes')
            return result
        if side.get('error'):
            # Existing workspace payloads expose the blob read limit as text.
            # Future structured reason flags can avoid even this narrow check.
            limited = 'byte read limit' in str(side['error'])
            result.update(status='too_large' if limited else 'unavailable',
                          reason='input_bytes' if limited else 'read_error')
            return result
        text = '' if side.get('absent') is True else side.get('text')
        if not isinstance(text, str):
            result['reason'] = 'missing_text'
            return result
        # Check characters before encoding to bound temporary allocations too.
        if len(text) > MAX_INPUT_BYTES or len(text.encode('utf-8', 'surrogatepass')) > MAX_INPUT_BYTES:
            result.update(status='too_large', reason='input_bytes')
            return result
        if '\0' in text:
            result['reason'] = 'binary'
            return result
        texts.append(text)
    before, after = (text.splitlines(keepends=True) for text in texts)
    summary = result['summary']
    summary.update(before_lines=len(before), after_lines=len(after))
    if any(len(line) > MAX_LINE_CHARS for lines in (before, after) for line in lines):
        result.update(status='too_large', reason='long_line')
        return result
    if max(len(before), len(after)) > MAX_LINES:
        result.update(status='too_large', reason='line_count')
        return result
    same = texts[0] == texts[1]
    if not same:
        if len(before) * len(after) > MAX_LINE_PAIRS:
            result.update(status='too_large', reason='comparison_budget')
            return result
        counts_a, counts_b = Counter(before), Counter(after)
        candidates = sum(count * counts_b.get(line, 0) for line, count in counts_a.items())
        if candidates > MAX_MATCH_CANDIDATES:
            result.update(status='too_large', reason='repeated_lines')
            return result
        # Disabling autojunk preserves repeated meaningful lines; the explicit
        # budgets above bound their quadratic matching cost instead.
        matcher = SequenceMatcher(None, before, after, autojunk=False)
        opcodes = matcher.get_opcodes()
        summary['inserted'] = sum(j2 - j1 for tag, _, _, j1, j2 in opcodes if tag in ('insert', 'replace'))
        summary['deleted'] = sum(i2 - i1 for tag, i1, i2, _, _ in opcodes if tag in ('delete', 'replace'))
        changes = {(i1, i2, j1, j2): number for number, (_, i1, i2, j1, j2) in
                   enumerate(code for code in opcodes if code[0] != 'equal')}
        summary['changes'] = len(changes)
        groups = list(matcher.get_grouped_opcodes(context))
    else:
        groups, changes = [], {}
    result['status'] = 'unchanged' if same else 'ok'
    if same and result['sides']['before']['absent'] != result['sides']['after']['absent']:
        result.update(status='ok', reason='empty_added' if result['sides']['before']['absent'] else 'empty_deleted')

    remaining = MAX_OUTPUT_ROWS
    gap_ranges = []
    previous_a = previous_b = 0
    for index, group in enumerate(groups):
        first, last = group[0], group[-1]
        a_start, b_start = first[1], first[3]
        if a_start > previous_a:
            gap_ranges.append((index, previous_a, a_start, previous_b, b_start))
        rows = []
        total = 0
        for tag, i1, i2, j1, j2 in group:
            change = changes.get((i1, i2, j1, j2)) if tag != 'equal' else None
            if tag == 'equal':
                total += i2 - i1
                for offset in range(min(i2 - i1, remaining)):
                    rows.append(_row('equal', before[i1 + offset], i1 + offset + 1, j1 + offset + 1))
                    remaining -= 1
            else:
                if tag in ('delete', 'replace'):
                    total += i2 - i1
                    for i in range(i1, min(i2, i1 + remaining)):
                        rows.append(_row('delete', before[i], i + 1, None, change))
                        remaining -= 1
                if tag in ('insert', 'replace'):
                    total += j2 - j1
                    for j in range(j1, min(j2, j1 + remaining)):
                        rows.append(_row('insert', after[j], None, j + 1, change))
                        remaining -= 1
        result['hunks'].append({'id': index, 'before_start': a_start + 1,
                                'before_count': last[2] - a_start,
                                'after_start': b_start + 1, 'after_count': last[4] - b_start,
                                'rows': rows, 'omitted_rows': total - len(rows)})
        previous_a, previous_b = last[2], last[4]
    if previous_a < len(before):
        gap_ranges.append((len(groups), previous_a, len(before), previous_b, len(after)))
    # Allocate changed hunks first, then optional unchanged expansion content.
    for index, i1, i2, j1, j2 in gap_ranges:
        count = i2 - i1
        shown = min(count, remaining)
        rows = [_row('equal', before[i1 + n], i1 + n + 1, j1 + n + 1) for n in range(shown)]
        remaining -= shown
        result['gaps'].append({'before_hunk': index, 'before_start': i1 + 1,
                               'after_start': j1 + 1, 'count': count,
                               'rows': rows, 'omitted_rows': count - shown})
    all_blocks = result['hunks'] + result['gaps']
    summary['shown_rows'] = sum(len(block['rows']) for block in all_blocks)
    summary['omitted_rows'] = sum(block['omitted_rows'] for block in all_blocks)
    summary['shown_changes'] = len({row['change'] for hunk in result['hunks'] for row in hunk['rows'] if row['change'] is not None})
    if any(hunk['omitted_rows'] for hunk in result['hunks']):
        result.update(status='truncated', reason='output_budget')
    # Omitting only equal lines does not make the change comparison incomplete.
    result['unchanged_content_limited'] = any(gap['omitted_rows'] for gap in result['gaps'])
    return result
