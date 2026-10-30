"""The service, not browser heuristics, determines available version actions."""
import unittest
from reprise.version_actions import version_actions, cleanup_actions
from reprise.service import Reprise
from test_runtime import fixture, commit_repo


class VersionActionTests(unittest.TestCase):
    def project(self, kind='git', adapter=None, approved=False):
        return {'id': 'project', 'revision': 'a' * 40, 'kind': kind,
                'recipe': {'adapter': adapter} if adapter else None,
                'recipe_approved': approved}

    def evidence(self, **changes):
        item = {'sha': 'a' * 40, 'kind': 'image', 'url': '/artifacts/exact.png', **changes}
        return [{'id': 'picture', 'project_id': 'project', 'items': [item]}]

    def test_recipe_approval_controls_execution_for_every_project_kind(self):
        for kind in ('git', 'folder', 'archive'):
            for adapter in ('static-web', 'command-web'):
                for approved in (False, True):
                    with self.subTest(kind=kind, adapter=adapter, approved=approved):
                        result = version_actions(self.project(kind, adapter, approved), self.evidence())
                        self.assertEqual(result['preview']['mode'], 'run' if approved else 'configure')
                        self.assertIsNone(result['preview']['media'])

    def test_nonrunnable_archive_uses_only_its_exact_project_and_version_picture(self):
        project = self.project('archive', 'manual')
        result = version_actions(project, self.evidence())
        self.assertEqual(result['preview'], {'mode': 'saved', 'media': {'record': 'picture', 'index': 0}})
        for changes in ({'sha': 'b' * 40}, {'missing': True}, {'error': 'outside evidence'},
                        {'url': None}, {'kind': 'file'}):
            self.assertEqual(version_actions(project, self.evidence(**changes))['preview']['mode'], 'recover')
        records = self.evidence()
        records[0]['project_id'] = 'another-project'
        self.assertEqual(version_actions(project, records)['preview']['mode'], 'recover')
        self.assertEqual(version_actions(project, [])['preview']['mode'], 'recover')

    def test_normal_projects_without_a_recipe_keep_explicit_configuration(self):
        for kind in ('git', 'folder'):
            result = version_actions(self.project(kind), self.evidence())
            self.assertEqual(result['preview']['mode'], 'configure')
            self.assertEqual(result['recovery']['mode'], 'copy')

    def test_deletion_effects_are_shared_by_the_version_and_cleanup_contracts(self):
        for kind in ('git', 'archive', 'folder'):
            effect = version_actions(self.project(kind), [])['removal']['effect']
            for managed in (False, True):
                result = cleanup_actions(kind, managed)
                self.assertEqual(result['choices'][0]['effect'], effect)
                self.assertTrue(result['choices'][0]['enabled'])
                self.assertEqual(result['choices'][1]['enabled'], managed)
                self.assertEqual(result['default'], 'environment' if managed else 'all')

    def test_real_service_exposes_exact_action_identity_and_keeps_source(self):
        root = fixture('version-actions')
        repository = commit_repo(root / 'source')
        app = Reprise(root / 'data')
        self.addCleanup(app.close)
        project = app.projects.add(str(repository.path))
        sha = repository.resolve('HEAD')
        before = (repository.path / 'index.html').read_bytes()
        result = app.version(project['id'], sha)
        self.assertEqual(result['actions']['project_id'], project['id'])
        self.assertEqual(result['actions']['sha'], sha)
        self.assertEqual(result['actions']['schema'], 1)
        self.assertEqual(result['actions']['preview']['mode'], 'configure')
        self.assertEqual((repository.path / 'index.html').read_bytes(), before)

    def test_stale_runtime_recipe_is_rejected_before_any_job_or_copy(self):
        root = fixture('version-actions-stale-recipe')
        repository = commit_repo(root / 'source')
        app = Reprise(root / 'data')
        self.addCleanup(app.close)
        project = app.projects.add(str(repository.path))
        sha = repository.resolve('HEAD')
        app.projects.save_recipe(project['id'], {'adapter': 'static-web'}, sha)
        old_hash = app.version(project['id'], sha)['recipe_hash']
        app.projects.save_recipe(project['id'], {'adapter': 'static-web', 'root': 'changed-root'}, sha)
        before_jobs = app.jobs.list()
        before_runtimes = app.runtime_list()
        for operation in ('run', 'capture'):
            with self.assertRaisesRegex(ValueError, '运行配置已经变化'):
                app.execute(project['id'], operation, {'sha': sha, 'recipe_hash': old_hash})
        self.assertEqual(app.jobs.list(), before_jobs)
        self.assertEqual(app.runtime_list(), before_runtimes)
