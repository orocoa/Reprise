import json
import os
from pathlib import Path
import tempfile
import unittest

from reprise.ai import AIService, validate_endpoint, validate_proposal


NOTES = {'zh': {'title': '静态站点', 'summary': '可直接采集。', 'changes': ['提交包含 HTML 入口']},
         'en': {'title': 'Static site', 'summary': 'Ready for capture.', 'changes': ['Commit contains an HTML entry']}}


class Stub:
    def __init__(self): self.calls = []
    def complete(self, config, messages):
        self.calls.append((config, messages))
        return {'model': config['model'], 'text': json.dumps({'localizations': NOTES, 'evidence_paths': ['index.html'], 'recipe': {'schema': 1, 'adapter': 'static-web'}})}


class AIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.adapter = Stub()
        self.ai = AIService(self.temp.name, self.adapter)
        self.context = {'project_id': 'one', 'sha': 'a' * 40, 'paths': ['index.html']}

    def test_disabled_core_has_no_requests_and_private_config(self):
        self.assertFalse(self.ai.state()['enabled'])
        with self.assertRaises(ValueError): self.ai.suggest(self.context)
        self.assertEqual(self.adapter.calls, [])
        state = self.ai.save({'enabled': True, 'endpoint': 'https://models.example/v1', 'model': 'user-exact-model', 'api_key': 'secret-one'})
        self.assertNotIn('api_key', state)
        self.assertTrue(state['has_key'])
        self.assertEqual(os.stat(self.ai.file).st_mode & 0o777, 0o600)

    def test_proposal_is_validated_cached_never_approved(self):
        self.ai.save({'enabled': True, 'endpoint': 'https://models.example/v1', 'model': 'user-exact-model', 'api_key': 'secret-one'})
        result = self.ai.suggest(self.context)
        self.assertFalse(result['approved'])
        self.assertTrue(result['requires_review'])
        self.assertEqual(result['requested_model'], 'user-exact-model')
        self.assertEqual(result['recipe']['adapter'], 'static-web')
        self.assertTrue(self.ai.suggest(self.context)['cached'])
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.ai.state()['metrics'], {'calls': 1, 'successes': 1})

    def test_bad_recipe_or_fabricated_path_rejected(self):
        with self.assertRaises(ValueError):
            validate_proposal(json.dumps({'localizations': NOTES, 'evidence_paths': ['invented'], 'recipe': None}), {'index.html'})
        with self.assertRaises(ValueError):
            validate_proposal(json.dumps({'localizations': NOTES, 'evidence_paths': [], 'recipe': {'adapter': 'static-web', 'root': '../../'}}), set())

    def test_both_languages_generated_once_and_missing_language_rejected(self):
        self.ai.save({'enabled': True, 'endpoint': 'https://models.example/v1', 'model': 'exact'})
        result = self.ai.suggest(self.context)
        self.assertEqual(result['localizations'], NOTES)
        self.assertEqual(result['sha'], self.context['sha'])
        self.assertIn('必须一次返回完整中英两版', self.adapter.calls[0][1][0]['content'])
        with self.assertRaises(ValueError):
            validate_proposal(json.dumps({'localizations': {'zh': NOTES['zh']}, 'recipe': None}), set())

    def test_clear_key_preserves_model_and_does_not_call_provider(self):
        self.ai.save({'enabled': True, 'endpoint': 'https://models.example/v1', 'model': 'exact', 'api_key': 'secret'})
        self.assertTrue(self.ai.save({'enabled': True})['has_key'])
        state = self.ai.save({'enabled': True, 'clear_key': True})
        self.assertFalse(state['has_key'])
        self.assertEqual(state['model'], 'exact')
        self.assertEqual(self.adapter.calls, [])
        with self.assertRaises(ValueError): self.ai.save({'enabled': True, 'clear_key': 'yes'})

    def test_endpoint_no_redirect_credential_or_remote_plaintext(self):
        for value in ('http://remote.example/v1', 'https://user:pw@example.org', 'https://example.org?key=secret'):
            with self.assertRaises(ValueError): validate_endpoint(value)
        self.assertEqual(validate_endpoint('http://127.0.0.1:9999/v1/'), 'http://127.0.0.1:9999/v1')

    def test_disabling_while_request_returns_discards_response(self):
        self.ai.save({'enabled': True, 'endpoint': 'https://models.example/v1', 'model': 'chosen'})
        original = self.adapter.complete
        def late(config, messages):
            self.ai.save({'enabled': False})
            return original(config, messages)
        self.adapter.complete = late
        with self.assertRaises(ValueError): self.ai.suggest(self.context)
        self.assertEqual(list((self.ai.directory / 'proposals').glob('*.json')), [])

class CompatibleTransportTests(unittest.TestCase):
    def test_local_http_preserves_model_and_blocks_redirect(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        from reprise.ai import CompatibleProvider
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                raw = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, raw, self.headers.get('Authorization')))
                if self.path.startswith('/redirect'):
                    self.send_response(302); self.send_header('Location', '/leak'); self.end_headers(); return
                data = json.dumps({'model': raw['model'], 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"summary":"test","recipe":null}'}}]}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            endpoint = 'http://127.0.0.1:%d' % server.server_port
            config = {'endpoint': endpoint + '/v1', 'model': 'exact-selected-model', 'api_key': 'test-key'}
            provider = CompatibleProvider()
            self.assertEqual(provider.complete(config, [{'role': 'user', 'content': 'test'}])['model'], 'exact-selected-model')
            self.assertEqual(requests[0][0], '/v1/chat/completions')
            self.assertEqual(requests[0][2], 'Bearer test-key')
            config['endpoint'] = endpoint + '/redirect'
            with self.assertRaises(ValueError): provider.complete(config, [{'role': 'user', 'content': 'test'}])
            self.assertEqual(len(requests), 2)
        finally:
            server.shutdown(); server.server_close(); thread.join(2)


if __name__ == '__main__': unittest.main()
