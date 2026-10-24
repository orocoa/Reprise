"""Line comparison content, incomplete inputs, and computation/output budgets."""
import unittest
from unittest.mock import patch

from reprise.text_diff import build_text_diff, MAX_OUTPUT_ROWS


def compare(before, after, **kwargs):
    return build_text_diff({'before': {'text': before}, 'after': {'text': after}}, **kwargs)


def ordered_rows(result):
    gaps = {gap['before_hunk']: gap for gap in result['gaps']}
    rows = []
    for number, hunk in enumerate(result['hunks']):
        rows.extend(gaps.get(number, {}).get('rows', []))
        rows.extend(hunk['rows'])
    rows.extend(gaps.get(len(result['hunks']), {}).get('rows', []))
    return rows


def reassemble(rows, side):
    endings = {'lf': '\n', 'crlf': '\r\n', 'cr': '\r', 'none': ''}
    return ''.join(row['text'] + endings[row['eol']] for row in rows if row[side + '_line'] is not None)


class TextDiffTests(unittest.TestCase):
    def test_insert_delete_replace_reconstruct_exact_files(self):
        before = 'first\nkeep\nold\nlast\n'
        after = 'first\nnew\nkeep\nreplacement\nlast\nextra'
        result = compare(before, after)
        rows = ordered_rows(result)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(reassemble(rows, 'before'), before)
        self.assertEqual(reassemble(rows, 'after'), after)
        self.assertEqual(result['summary']['deleted'], 1)
        self.assertEqual(result['summary']['inserted'], 3)
        self.assertEqual([r['before_line'] for r in rows if r['before_line']], list(range(1, 5)))
        self.assertEqual([r['after_line'] for r in rows if r['after_line']], list(range(1, 7)))

    def test_context_gaps_can_expand_without_losing_line_numbers(self):
        before = ''.join('row %d\n' % i for i in range(40))
        after = before.replace('row 10\n', 'changed 10\n').replace('row 30\n', 'changed 30\n')
        result = compare(before, after, context=2)
        self.assertEqual(len(result['hunks']), 2)
        self.assertEqual(len(result['gaps']), 3)
        self.assertEqual(result['hunks'][0]['before_start'], 9)
        self.assertEqual(result['summary']['changes'], 2)
        self.assertEqual(reassemble(ordered_rows(result), 'before'), before)
        self.assertEqual(reassemble(ordered_rows(result), 'after'), after)

    def test_no_final_newline_and_crlf_are_actual_changes(self):
        for before, after in [('same\n', 'same'), ('same\r\n', 'same\n'), ('same\r', 'same\r\n')]:
            with self.subTest(before=repr(before), after=repr(after)):
                result = compare(before, after)
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(result['summary']['changes'], 1)
                self.assertEqual(reassemble(ordered_rows(result), 'before'), before)
                self.assertEqual(reassemble(ordered_rows(result), 'after'), after)

    def test_missing_is_not_empty_but_explicit_absence_is(self):
        missing = build_text_diff({'before': {}, 'after': {'text': 'new\n'}})
        self.assertEqual(missing['reason'], 'missing_text')
        added = build_text_diff({'before': {'text': '', 'absent': True}, 'after': {'text': 'new\n'}})
        self.assertEqual(added['summary']['inserted'], 1)
        self.assertEqual(ordered_rows(added)[0]['before_line'], None)
        empty = build_text_diff({'before': {'absent': True}, 'after': {'text': ''}})
        self.assertEqual(empty['reason'], 'empty_added')
        self.assertEqual(empty['status'], 'ok')

    def test_binary_read_errors_and_partial_input_never_generate_fake_deletions(self):
        for side, status, reason in [
            ({'binary': True, 'text': ''}, 'unavailable', 'binary'),
            ({'text': 'a\0b'}, 'unavailable', 'binary'),
            ({'error': 'unreadable', 'text': ''}, 'unavailable', 'read_error'),
            ({'error': 'File exceeds the 65536-byte read limit: /private', 'text': ''}, 'too_large', 'input_bytes'),
            ({'truncated': True, 'text': 'partial'}, 'truncated', 'input_truncated')]:
            with self.subTest(side=side):
                result = build_text_diff({'before': {'text': 'original'}, 'after': side})
                self.assertEqual((result['status'], result['reason']), (status, reason))
                self.assertEqual(result['hunks'], [])
                self.assertNotIn('/private', str(result))

    def test_giant_text_giant_lines_and_line_counts_stop_before_matching(self):
        cases = [('字' * 30000, 'input_bytes'), ('x' * 9000, 'long_line'), ('x\n' * 4001, 'line_count')]
        with patch('reprise.text_diff.SequenceMatcher', side_effect=AssertionError('must not match')):
            for value, reason in cases:
                with self.subTest(reason=reason):
                    result = compare(value, 'other')
                    self.assertEqual((result['status'], result['reason']), ('too_large', reason))

    def test_repeated_lines_and_large_pair_space_are_bounded_before_matching(self):
        cases = [('same\n' * 1000, 'same\n' * 999 + 'changed\n', 'repeated_lines'),
                 (''.join('%d\n' % i for i in range(2100)), ''.join('%d!\n' % i for i in range(2100)), 'comparison_budget')]
        with patch('reprise.text_diff.SequenceMatcher', side_effect=AssertionError('must not match')):
            for before, after, reason in cases:
                self.assertEqual(compare(before, after)['reason'], reason)

    def test_output_budget_is_explicit_and_does_not_change_total_counts(self):
        result = compare('', 'new\n' * 3000)
        self.assertEqual(result['status'], 'truncated')
        self.assertEqual(result['summary']['inserted'], 3000)
        self.assertEqual(result['summary']['shown_rows'], MAX_OUTPUT_ROWS)
        self.assertEqual(result['summary']['omitted_rows'], 1000)
        self.assertEqual(len(ordered_rows(result)), MAX_OUTPUT_ROWS)

    def test_equal_content_needs_no_matcher_and_optional_expansion_is_bounded(self):
        value = 'same\n' * 3000
        with patch('reprise.text_diff.SequenceMatcher', side_effect=AssertionError('equality fast path')):
            result = compare(value, value)
        self.assertEqual(result['status'], 'unchanged')
        self.assertTrue(result['unchanged_content_limited'])
        self.assertEqual(result['summary']['changes'], 0)
        self.assertEqual(len(ordered_rows(result)), MAX_OUTPUT_ROWS)

    def test_context_zero_unicode_and_html_remain_exact_text(self):
        before, after = '<img src=x>\n你好\n🙂\n', '<script>evil</script>\n你好\n🙂\n'
        result = compare(before, after, context=0)
        self.assertEqual(len(result['hunks'][0]['rows']), 2)
        self.assertEqual(reassemble(ordered_rows(result), 'before'), before)
        self.assertEqual(reassemble(ordered_rows(result), 'after'), after)


if __name__ == '__main__':
    unittest.main()
