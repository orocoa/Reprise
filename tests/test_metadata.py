"""Native no-follow macOS ACL inspection retains the strict protection boundary."""
import os
import re
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from reprise.metadata import has_acl
from test_runtime import fixture


@unittest.skipUnless(sys.platform == 'darwin', 'Darwin native ACL contract')
class NativeACLTests(unittest.TestCase):
    def test_empty_acl_acl_entry_and_symlink_match_system_inspection(self):
        import pwd
        root = fixture('native-acl')
        plain = root / 'plain name\nline.txt';plain.write_bytes(b'unchanged')
        protected = root / 'protected.txt';protected.write_bytes(b'keep this synthetic file')
        subprocess.run(['/bin/chmod', '+a', 'user:'+pwd.getpwuid(os.getuid()).pw_name+' allow read', str(protected)], check=True)
        link = root / 'link';link.symlink_to(protected.name)
        for path in (root, plain, protected, link):
            observed = subprocess.run(['/bin/ls', '-lde', str(path)], capture_output=True, check=True).stdout
            expected = bool(re.search(rb'^\s+\d+:', observed, re.MULTILINE))
            # The implementation must no longer fork one process per file.
            with patch('subprocess.run', side_effect=AssertionError('Native ACL must not spawn ls')):
                self.assertEqual(has_acl(path), expected)
        self.assertTrue(has_acl(protected))
        self.assertFalse(has_acl(plain))
        self.assertFalse(has_acl(link), 'A target ACL must not be attributed to its symlink')
        self.assertEqual(protected.read_bytes(), b'keep this synthetic file')
        with self.assertRaises(OSError):
            has_acl(root / 'missing')

    def test_acl_access_errors_are_not_treated_as_absent_permissions(self):
        import ctypes
        import errno
        from types import SimpleNamespace
        root = fixture('native-acl-denied')
        target = root / 'file';target.write_bytes(b'keep')
        def denied(*args):
            ctypes.set_errno(errno.EACCES)
            return None
        with patch('reprise.metadata.native', return_value=SimpleNamespace(acl_get_link_np=denied)):
            with self.assertRaises(PermissionError):
                has_acl(target)
