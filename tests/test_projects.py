import hashlib
import json
import os
import subprocess
import sys
import threading
import tempfile
import unittest
from pathlib import Path

from reprise.projects import ProjectStore
from reprise.service import Reprise
from test_git import git


COMMAND_RECIPE = {'schema': 1, 'adapter': 'command-web', 'commands': {'start': ['python3', '-m', 'http.server', '{port}']}}


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        self.store = ProjectStore(self.root / 'state')

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, files):
        for name, data in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-m', 'fixture')
        return git(self.source, 'rev-parse', 'HEAD')

    def test_refresh_observes_new_commits_and_old_version_detection(self):
        first = self.commit({'data.csv': 'one,two'})
        project = self.store.add(str(self.source), 'Generic project')
        self.assertEqual(project['head'], first)
        self.assertEqual(project['detected']['kind'], 'unknown')
        second = self.commit({'index.html': '<h1>Now a website</h1>'})
        refreshed = self.store.get(project['id'])
        self.assertEqual(refreshed['head'], second)
        self.assertEqual(refreshed['recipe']['adapter'], 'static-web')
        old = self.store.get(project['id'], first)
        self.assertEqual(old['revision'], first)
        self.assertEqual(old['detected']['kind'], 'unknown')
        self.assertIsNone(old['recipe'])
        self.assertEqual(len(self.store.repository(project['id']).history()['commits']), 2)

    def test_import_deduplicates_canonical_path_and_is_read_only(self):
        self.commit({'index.html': '<h1>Committed</h1>'})
        (self.source / 'index.html').write_text('Uncommitted')
        before_index = (self.source / '.git/index').read_bytes()
        before_config = (self.source / '.git/config').read_bytes()
        project = self.store.add(str(self.source))
        self.assertEqual(self.store.add(str(self.source / '.git' / '..'))['id'], project['id'])
        self.assertEqual(len(self.store.records()), 1)
        self.assertEqual((self.source / 'index.html').read_text(), 'Uncommitted')
        self.assertEqual((self.source / '.git/index').read_bytes(), before_index)
        self.assertEqual((self.source / '.git/config').read_bytes(), before_config)
        self.assertTrue(self.store.repository(project['id']).status()['dirty'])

    def test_committed_command_requires_save_and_old_versions_stay_distinct(self):
        old = self.commit({'index.html': '<h1>Static</h1>'})
        current = self.commit({'.reprise.json': json.dumps(COMMAND_RECIPE)})
        app = Reprise(self.root / 'service')
        try:
            project = app.projects.add(str(self.source))
            self.assertEqual(project['recipe_source'], 'repository')
            self.assertFalse(project['recipe_approved'])
            with self.assertRaisesRegex(ValueError, '配方'):
                app.execute(project['id'], 'run', {'sha': current})
            self.assertFalse(list((self.root / 'service/runtimes').glob('*/snapshot')))
            previous = app.projects.get(project['id'], old)
            self.assertEqual(previous['recipe_source'], 'detected')
            saved = app.projects.save_recipe(project['id'], project['recipe'])
            self.assertEqual(saved['recipe_source'], 'project')
            self.assertTrue(saved['recipe_approved'])
            reset = app.projects.save_recipe(project['id'], None)
            self.assertEqual(reset['recipe_source'], 'repository')
            self.assertFalse(reset['recipe_approved'])
        finally:
            app.close()

    def test_empty_and_bare_repositories_are_browsable(self):
        empty = self.store.add(str(self.source))
        self.assertEqual(empty['detected']['kind'], 'empty')
        self.assertEqual(self.store.repository(empty['id']).history()['commits'], [])
        self.assertTrue(empty['detected']['capabilities']['history'])
        sha = self.commit({'readme.md': 'Example'})
        bare = self.root / 'bare.git'
        git(self.root, 'clone', '--bare', str(self.source), str(bare))
        project = self.store.add(str(bare))
        self.assertTrue(project['repository']['bare'])
        self.assertEqual(project['head'], sha)
        self.assertFalse(self.store.repository(project['id']).status()['available'])

    def test_invalid_committed_recipe_reports_error_without_fallback_execution(self):
        self.commit({'index.html': '<h1>static</h1>', '.reprise.json': '{"adapter":"shell"}'})
        project = self.store.add(str(self.source))
        self.assertIsNone(project['recipe'])
        self.assertEqual(project['recipe_source'], 'repository')
        self.assertTrue(project['recipe_error'])
        self.assertFalse(project['recipe_approved'])

    def test_shallow_version_preserves_identity_when_diff_parent_missing(self):
        parent = self.commit({'readme.md': 'Initial'})
        sha = self.commit({'index.html': '<h1>Current</h1>'})
        shallow = self.root / 'shallow'
        git(self.root, 'clone', '--depth=1', self.source.as_uri(), str(shallow))
        app = Reprise(self.root / 'service')
        try:
            project = app.projects.add(str(shallow))
            version = app.version(project['id'], sha)
            self.assertEqual(version['commit']['parents'], [parent])
            self.assertEqual(version['commit']['sha'], sha)
            self.assertEqual(version['detection']['kind'], 'static-web')
            self.assertFalse(version['diff']['available'])
            self.assertEqual(version['diff']['base'], parent)
            self.assertTrue(version['diff']['error'])
        finally:
            app.close()

    def test_cli_reads_preserve_live_job_and_other_process_cannot_overlap(self):
        app = Reprise(self.root / 'service')
        started, release = threading.Event(), threading.Event()
        def callback():
            started.set()
            release.wait(timeout=15)
            return {'ok': True}
        job = app.jobs.submit('same-project', 'capture', callback)
        try:
            self.assertTrue(started.wait(timeout=3))
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            cli = subprocess.run([sys.executable, '-m', 'reprise', '--data', str(app.directory), 'runtimes'],
                                 env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(app.jobs.get(job['id'])['status'], 'running')
            probe = 'from reprise.jobs import Jobs\nimport sys\njobs=Jobs(sys.argv[1])\ntry:\n jobs.submit("same-project", "capture", lambda: {})\nexcept ValueError:\n jobs.close(); sys.exit(0)\nelse:\n jobs.close(); sys.exit(2)'
            overlap = subprocess.run([sys.executable, '-c', probe, str(app.directory)],
                                     env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(overlap.returncode, 0, overlap.stderr)
            self.assertEqual(app.jobs.get(job['id'])['status'], 'running')
        finally:
            release.set()
            app.close()
        self.assertEqual(app.jobs.get(job['id'])['status'], 'complete')

    def test_unknown_type_version_still_has_root_file_diff(self):
        sha = self.commit({'opaque.dat': 'unknown data'})
        app = Reprise(self.root / 'service')
        try:
            project = app.projects.add(str(self.source))
            version = app.version(project['id'], sha)
            self.assertEqual(version['commit']['sha'], sha)
            self.assertEqual(version['diff']['files'][0]['path'], 'opaque.dat')
            self.assertEqual(version['diff']['counts']['added'], 1)
            self.assertTrue(version['detection']['capabilities']['manual'])
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main()
