import copy
import datetime
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup_ci', ROOT / 'scripts/cleanup_ci_artifacts.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
REPO = 'owner/example'


def run(rid, sha, event='push', branch='main'):
    created = (datetime.datetime(2026, 11, 1) + datetime.timedelta(minutes=rid)).isoformat() + 'Z'
    return {'id': rid, 'head_sha': sha, 'event': event, 'head_branch': branch,
            'head_repository': {'full_name': REPO}, 'path': '.github/workflows/ci.yml',
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'created_at': created}


def artifacts(rid):
    return [{'id': rid * 10 + i, 'name': 'reprise-%s-py%s-1' % (os_name, python),
             'size_in_bytes': 10, 'digest': 'sha256:' + 'a' * 64,
             'expired': False, 'workflow_run': {'id': rid}}
            for i, (os_name, python, _) in enumerate(ci.MATRIX)]


def snapshot():
    runs = [run(30, 'd' * 40), run(20, 'b' * 40, 'pull_request', 'release'),
            run(21, 'c' * 40, 'pull_request', 'previous'),
            run(25, 'e' * 40, 'pull_request', 'current-source'),
            run(10, 'a' * 40), run(15, 'g' * 40, 'pull_request', 'merged'),
            run(50, 'h' * 40, 'pull_request', 'open'),
            run(60, 'i' * 40, 'pull_request', 'unmerged'), run(70, 'z' * 40, 'pull_request', 'unknown')]
    prs = {30: [{'state': 'closed', 'merged_at': 'date', 'merge_commit_sha': 'd' * 40,
                 'head': {'sha': 'e' * 40}}],
           15: [{'state': 'closed', 'merged_at': 'date', 'merge_commit_sha': 'a' * 40}],
           50: [{'state': 'open', 'merged_at': None}],
           60: [{'state': 'closed', 'merged_at': None}]}
    return {'repository': REPO, 'default_branch': 'main', 'main_sha': 'd' * 40,
            'runs': runs, 'artifacts': [a for r in runs for a in artifacts(r['id'])],
            'jobs': {r['id']: [{'name': name, 'conclusion': 'success'} for name in ci.JOB_NAMES] for r in runs},
            'pulls': prs, 'release_shas': ['b' * 40, 'c' * 40],
            'covered_commits': ['a' * 40, 'd' * 40], 'release_fingerprint': {'example': True}}


class ArtifactLifecycleTests(unittest.TestCase):
    def test_only_verified_superseded_main_and_merged_pr_are_deleted(self):
        plan = ci.plan_cleanup(snapshot())
        self.assertEqual({a['runId'] for a in plan['delete']}, {10, 15})
        self.assertEqual({a['runId'] for a in plan['keep']}, {20, 21, 25, 30, 50, 60, 70})

    def test_failed_platform_or_missing_artifact_preserves_everything(self):
        for change in ('job', 'artifact', 'head'):
            data = snapshot()
            if change == 'job':
                data['jobs'][30][0]['conclusion'] = 'failure'
            elif change == 'artifact':
                data['artifacts'] = [a for a in data['artifacts'] if a['id'] != 300]
            else:
                data['main_sha'] = 'f' * 40
            plan = ci.plan_cleanup(data)
            self.assertEqual(plan['state'], 'waiting')
            self.assertEqual(plan['delete'], [])

    def test_formal_release_missing_full_evidence_keeps_partial_recovery(self):
        data = snapshot()
        data['artifacts'] = [a for a in data['artifacts'] if a['id'] != 200]
        plan = ci.plan_cleanup(data)
        self.assertTrue({201, 202} <= {a['id'] for a in plan['keep']})

    def test_unknown_artifact_and_foreign_repository_are_not_touched(self):
        data = snapshot()
        data['artifacts'].append(dict(artifacts(10)[0], id=9999, name='manual-recovery.zip'))
        next(r for r in data['runs'] if r['id'] == 15)['head_repository'] = {'full_name': 'fork/example'}
        plan = ci.plan_cleanup(data)
        self.assertTrue({9999, 150, 151, 152} <= {a['id'] for a in plan['keep']})

    def test_superseded_attempt_is_removed_only_after_complete_retry(self):
        data = snapshot()
        current = next(r for r in data['runs'] if r['id'] == 30)
        current['run_attempt'] = 2
        new = [dict(a, id=a['id'] + 90000, name=a['name'][:-1] + '2') for a in artifacts(30)]
        data['artifacts'].extend(new)
        plan = ci.plan_cleanup(data)
        self.assertTrue({300, 301, 302} <= {a['id'] for a in plan['delete']})
        self.assertTrue({90300, 90301, 90302} <= {a['id'] for a in plan['keep']})
        data['artifacts'].remove(new[-1])
        self.assertEqual(ci.plan_cleanup(data)['delete'], [])

    def test_no_age_or_size_cutoff_and_saved_snapshot_replays(self):
        data = snapshot()
        for a in data['artifacts']:
            a['created_at'] = '2001-01-01T00:00:00Z'
            a['size_in_bytes'] = 10 ** 12
        import json
        replay = json.loads(json.dumps(data))
        plan = ci.plan_cleanup(replay)
        self.assertTrue({300, 301, 302} <= {a['id'] for a in plan['keep']})
        self.assertEqual({a['runId'] for a in plan['delete']}, {10, 15})

    def test_moving_main_or_release_stops_before_any_delete(self):
        data = snapshot()
        class API:
            def get(self, path):
                return {'sha': 'changed'}
            def delete_artifact(self, aid):
                raise AssertionError('must never delete')
        with patch.object(ci, 'release_state', return_value=(data['release_fingerprint'], [])):
            self.assertEqual(ci.apply_plan(API(), data, ci.plan_cleanup(data), Path('unused')), [])

    def test_changed_artifact_identity_cannot_be_deleted(self):
        data = snapshot()
        class API:
            def get(self, path):
                if path.startswith('commits/'):
                    return {'sha': data['main_sha']}
                if path.startswith('actions/runs/'):
                    return next(r for r in data['runs'] if r['id'] == 30)
                return dict(artifacts(10)[0], digest='changed')
            def pages(self, path, key):
                return data['jobs'][30] if key == 'jobs' else artifacts(30)
            def delete_artifact(self, aid):
                raise AssertionError('must never delete')
        with patch.object(ci, 'release_state', return_value=(data['release_fingerprint'], [])):
            with self.assertRaises(ValueError):
                ci.apply_plan(API(), data, ci.plan_cleanup(data), Path('unused'))

    def test_missing_live_replacement_or_changed_release_prevents_deletion(self):
        data = snapshot()
        class API:
            def get(self, path):
                if path.startswith('commits/'):
                    return {'sha': data['main_sha']}
                return next(r for r in data['runs'] if r['id'] == 30)
            def pages(self, path, key):
                return data['jobs'][30] if key == 'jobs' else artifacts(30)[:2]
            def delete_artifact(self, aid):
                raise AssertionError('must never delete')
        for fingerprint in (data['release_fingerprint'], {'changed': True}):
            with patch.object(ci, 'release_state', return_value=(fingerprint, [])):
                self.assertEqual(ci.apply_plan(API(), data, ci.plan_cleanup(data), Path('unused')), [])

    def test_delete_endpoint_is_scoped_to_exact_artifact_ids(self):
        api = ci.GitHub(REPO)
        with patch.object(ci.subprocess, 'run') as run_mock:
            for aid in [-1, 0, '12', True]:
                with self.assertRaises(ValueError):
                    api.delete_artifact(aid)
            run_mock.assert_not_called()
            api.delete_artifact(12)
            self.assertEqual(run_mock.call_args.args[0][-1], 'repos/owner/example/actions/artifacts/12')

    def test_incomplete_new_release_does_not_displace_two_usable_releases(self):
        names = ['ARTIFACTS.json', 'SHA256SUMS.txt', 'Reprise-Skill.zip',
                 'reprise-workbuddy.zip', 'package.whl', 'package.tar.gz']
        releases = [{'id': i, 'tag_name': 'v%s' % i, 'target_commitish': 'sha',
                     'draft': False, 'prerelease': False, 'published_at': '2026-11-%02d' % i,
                     'assets': [] if i == 3 else [{'id': j, 'name': n, 'state': 'uploaded', 'size': 1, 'digest': 'ok'} for j, n in enumerate(names)]}
                    for i in [3, 2, 1]]
        class API:
            def pages(self, path):
                return releases
            def get(self, path):
                return {'object': {'type': 'commit', 'sha': path[-1] * 40}}
        fingerprint, shas = ci.release_state(API())
        self.assertEqual(shas, ['3' * 40, '2' * 40, '1' * 40])
        self.assertEqual(len(fingerprint['stableRefs']), 3)


if __name__ == '__main__':
    unittest.main()
