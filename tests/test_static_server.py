"""Directory URLs preserve relative assets without escaping the preview origin."""
import http.client
from pathlib import Path
import threading
import unittest
from urllib.parse import urljoin

from reprise.static_server import LoopbackHTTPServer, PreviewHandler
from test_runtime import fixture


class StaticDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = fixture('static-directory')
        self.root = self.directory / 'source'
        self.root.mkdir()
        for name in ('docs', 'nested/中文 空格', 'evil.invalid'):
            folder = self.root / name
            folder.mkdir(parents=True)
            (folder / 'index.html').write_text('<script src="app.js"></script>')
            (folder / 'app.js').write_text('document.title = "directory asset";')
        self.server = LoopbackHTTPServer(('127.0.0.1', 0), PreviewHandler)
        self.server.root = self.root.resolve()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, method='GET', host=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            connection.request(method, path, headers={'Host': host or '127.0.0.1:%s' % self.server.server_port})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_directory_redirect_keeps_query_and_relative_scripts(self):
        for method in ('GET', 'HEAD'):
            for requested, expected in (
                    ('/docs?theme=dark&return=%2F', '/docs/?theme=dark&return=%2F'),
                    ('/nested/%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC?q=a%20b',
                     '/nested/%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC/?q=a%20b')):
                with self.subTest(method=method, path=requested):
                    status, headers, body = self.request(requested, method)
                    self.assertEqual(status, 301)
                    self.assertEqual(headers['Location'], expected)
                    self.assertEqual(headers['Content-Length'], '0')
                    self.assertEqual(body, b'')
                    self.assertEqual(self.request(expected)[0], 200)
                    asset = self.request(urljoin(expected, 'app.js'))
                    self.assertEqual(asset[0], 200)
                    self.assertIn(b'directory asset', asset[2])

    def test_redirects_cannot_change_origin_or_bypass_path_and_host_checks(self):
        (self.directory / 'outside').mkdir()
        (self.root / 'leak').symlink_to(self.directory / 'outside')
        for path, expected in (('/%2f%2fevil.invalid', 301), ('/%2e%2e/outside', 403),
                               ('/leak', 403), ('http://evil.invalid/docs', 400),
                               ('/%00', 400), ('/%ff', 400)):
            with self.subTest(path=path):
                status, headers, _ = self.request(path)
                self.assertEqual(status, expected)
                if status == 301:
                    self.assertEqual(headers['Location'], '/evil.invalid/')
                else:
                    self.assertNotIn('Location', headers)
        status, headers, _ = self.request('/docs', host='evil.invalid')
        self.assertEqual(status, 403)
        self.assertNotIn('Location', headers)


if __name__ == '__main__':
    unittest.main()
