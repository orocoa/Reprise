"""Shared JSON storage retains mandatory-record and symlink boundaries."""
import json
import unittest

from reprise import runtime, storage
from test_runtime import fixture


class StorageTests(unittest.TestCase):
    def test_optional_and_required_reads_keep_distinct_missing_semantics(self):
        path = fixture('storage') / 'record.json'
        self.assertEqual(storage.read_json(path, {'empty': True}), {'empty': True})
        with self.assertRaises(FileNotFoundError):
            runtime.read_json(path)
        runtime.write_json(path, {'text': '保留内容'})
        self.assertEqual(storage.read_json(path), runtime.read_json(path))
        path.write_text('{invalid')
        for reader in (runtime.read_json, storage.read_json):
            with self.assertRaises(json.JSONDecodeError):
                reader(path)
        self.assertEqual(path.read_text(), '{invalid')

    def test_shared_runtime_helpers_refuse_state_symlinks(self):
        directory = fixture('storage-symlinks')
        target = directory / 'original.json'
        target.write_text('{"original": true}')
        link = directory / 'linked.json'
        link.symlink_to(target)
        for helper in (runtime.read_json, lambda path: runtime.write_json(path, {'changed': True})):
            with self.assertRaisesRegex(ValueError, '符号链接'):
                helper(link)
        self.assertEqual(target.read_text(), '{"original": true}')
        missing_link = directory / 'dangling.json'
        missing_link.symlink_to(directory / 'missing.json')
        with self.assertRaisesRegex(ValueError, '符号链接'):
            runtime.read_json(missing_link)


if __name__ == '__main__':
    unittest.main()
