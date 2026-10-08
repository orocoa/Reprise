import unittest
from reprise.recipes import recipe_hash, validate_recipe


class RecipeTests(unittest.TestCase):
    def test_deterministic_defaults(self):
        recipe = validate_recipe({'adapter': 'static-web'})
        self.assertEqual(recipe['captures'][0]['viewport']['scale'], 2)
        self.assertEqual(recipe_hash(recipe), recipe_hash({'adapter': 'static-web'}))
        self.assertEqual(recipe['network'], 'local')

    def test_paths_and_unexpected_code_rejected(self):
        for root in ['../outside', '/tmp', 'nested/../../out', '..\\outside', 'C:/path']:
            with self.subTest(root=root), self.assertRaises(ValueError):
                validate_recipe({'adapter': 'static-web', 'root': root})
        for route in ['https://example.com', '//example.com', '/\\example.com', 'javascript:alert(1)']:
            with self.subTest(route=route), self.assertRaises(ValueError):
                validate_recipe({'adapter': 'static-web', 'captures': [{'id': 'x', 'route': route}]})
        with self.assertRaises(ValueError):
            validate_recipe({'adapter': 'static-web', 'commands': {'start': ['echo', 'x']}})
        with self.assertRaises(ValueError):
            validate_recipe({'adapter': 'command-web', 'commands': {'start': 'node server.js'}})
        with self.assertRaises(ValueError):
            validate_recipe({'adapter': 'static-web', 'captures': [{'steps': [{'action': 'evaluate', 'value': 'code'}]}]})

    def test_validated_game_recipe(self):
        recipe = validate_recipe({'adapter': 'command-web', 'commands': {'install': [['npm', 'ci']], 'build': [['npm', 'run', 'build']],
            'start': ['npm', 'run', 'preview', '--', '--host', '{host}', '--port', '{port}']},
            'captures': [{'id': 'game-start', 'wait_for': 'canvas', 'steps': [{'action': 'press', 'key': 'ArrowRight'},
                {'action': 'wait', 'ms': 120}], 'record': True, 'record_ms': 50}]})
        self.assertEqual(recipe['captures'][0]['steps'][0]['key'], 'ArrowRight')
        self.assertEqual(recipe['commands']['start'][-1], '{port}')

    def test_limits_and_unique_scenarios(self):
        invalid = [{'adapter': 'static-web', 'readiness': {'timeout_ms': True}},
                   {'adapter': 'static-web', 'captures': [{'id': 'x'}, {'id': 'x'}]},
                   {'adapter': 'static-web', 'captures': [{'id': '../../x'}]},
                   {'adapter': 'static-web', 'captures': [{'viewport': {'width': 999999}}]},
                   {'adapter': 'static-web', 'captures': [{'full_page': 'yes'}]}]
        for recipe in invalid:
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                validate_recipe(recipe)


if __name__ == '__main__':
    unittest.main()
