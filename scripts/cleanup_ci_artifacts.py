#!/usr/bin/env python3
"""Delete only CI artifacts replaced by a complete, verified main build.

No age/size cutoff, release mutation, run deletion, local cleanup or PR code execution.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

MATRIX = [('ubuntu-24.04', '3.9', '0'), ('ubuntu-latest', '3.13', '1'),
          ('macos-latest', '3.9', '1')]
JOB_NAMES = {'regression (%s, %s, %s)' % row for row in MATRIX}
ARTIFACT_NAME = re.compile(r'reprise-(?:ubuntu-(?:24\.04|latest)|macos-latest)-py3\.(?:9|13)-[1-9][0-9]*')


def full_set(run, artifacts, jobs, repository):
    if (run.get('status') != 'completed' or run.get('conclusion') != 'success' or
            (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower()):
        return set()
    if len(jobs) != 3 or {j.get('name') for j in jobs} != JOB_NAMES or any(j.get('conclusion') != 'success' for j in jobs):
        return set()
    selected = set()
    for os_name, python, _ in MATRIX:
        name = 'reprise-%s-py%s-%s' % (os_name, python, run.get('run_attempt', 1))
        found = [a for a in artifacts if a['name'] == name and not a.get('expired') and
                 a['size_in_bytes'] > 0 and a.get('digest')]
        if len(found) != 1:
            return set()
        selected.add(found[0]['id'])
    return selected


def plan_cleanup(snapshot):
    runs = {r['id']: r for r in snapshot['runs']}
    jobs = {int(k): v for k, v in snapshot['jobs'].items()}
    pulls = {int(k): v for k, v in snapshot['pulls'].items()}
    groups = defaultdict(list)
    for artifact in snapshot['artifacts']:
        groups[artifact['workflow_run']['id']].append(artifact)
    complete = {rid: full_set(runs[rid], rows, jobs.get(rid, []), snapshot['repository'])
                for rid, rows in groups.items() if rid in runs}
    main_runs = [r for r in runs.values() if r.get('event') == 'push' and
                 r.get('head_branch') == snapshot['default_branch'] and
                 r.get('head_sha') == snapshot['main_sha'] and complete.get(r['id'])]
    if not main_runs:
        return {'state': 'waiting', 'reason': 'No complete successful current-main replacement; preserve everything',
                'delete': [], 'keep': [{'id': a['id'], 'reason': 'replacement not verified'} for a in snapshot['artifacts']]}
    main = max(main_runs, key=lambda r: r['created_at'])
    protected, verified_runs = {}, set()

    def protect(run, reason):
        verified_runs.add(run['id'])
        for aid in complete[run['id']]:
            protected.setdefault(aid, reason)

    protect(main, 'latest complete successful main')
    # Keep the source CI behind the current merge until a later verified merge replaces it.
    current_prs = pulls.get(main['id'], [])
    candidate_shas = {p['head']['sha'] for p in current_prs
                      if p.get('merged_at') and p.get('merge_commit_sha') == main['head_sha']}
    for sha in candidate_shas:
        matches = [r for r in runs.values() if r['head_sha'] == sha and complete.get(r['id'])]
        if matches:
            protect(max(matches, key=lambda r: r['created_at']), 'validated source of current main merge')
    for sha in snapshot['release_shas']:
        matches = [r for r in runs.values() if r['head_sha'] == sha and complete.get(r['id'])]
        if matches:
            protect(max(matches, key=lambda r: r['created_at']), 'latest/previous stable release evidence')
        else:
            for rid, rows in groups.items():
                if runs.get(rid, {}).get('head_sha') == sha:
                    protected.update({a['id']: 'release evidence without a complete replacement' for a in rows})

    delete, keep = [], []
    for artifact in snapshot['artifacts']:
        aid, rid = artifact['id'], artifact['workflow_run']['id']
        run = runs.get(rid)
        reason = protected.get(aid)
        replace = None
        recognized = (run and run.get('status') == 'completed' and
                      run.get('path', '').split('@')[0] == '.github/workflows/ci.yml' and
                      (run.get('head_repository') or {}).get('full_name', '').lower() == snapshot['repository'].lower() and
                      ARTIFACT_NAME.fullmatch(artifact['name']))
        if not reason and recognized:
            if rid in verified_runs:
                replace = 'older attempt replaced by a verified complete attempt'
            elif (run.get('event') == 'push' and run.get('head_branch') == snapshot['default_branch'] and
                  run['created_at'] < main['created_at'] and
                  run['head_sha'] in snapshot['covered_commits']):
                replace = 'older main build replaced by verified descendant'
            elif run.get('event') == 'pull_request':
                prs = pulls.get(rid, [])
                if prs and all(p.get('state') == 'closed' and p.get('merged_at') and
                               p.get('merge_commit_sha') in snapshot['covered_commits'] for p in prs):
                    replace = 'merged PR covered by verified main build'
        row = {'id': aid, 'name': artifact['name'], 'runId': rid,
               'bytes': artifact['size_in_bytes'], 'digest': artifact.get('digest')}
        if replace:
            delete.append(dict(row, reason=replace))
        else:
            keep.append(dict(row, reason=reason or 'active, unmerged, unknown, or replacement not verified'))
    return {'state': 'ready', 'mainRun': main['id'], 'mainSha': main['head_sha'],
            'delete': delete, 'keep': keep}


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository')
        self.prefix = 'repos/' + repository

    def get(self, path=''):
        endpoint = self.prefix + ('/' + path if path else '')
        return json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))

    def pages(self, path, key=None):
        endpoint = self.prefix + '/' + path
        pages = json.loads(subprocess.check_output(['gh', 'api', endpoint, '--paginate', '--slurp'], text=True))
        return [row for page in pages for row in (page[key] if key else page)]

    def delete_artifact(self, aid):
        if type(aid) is not int or aid < 1:
            raise ValueError('Exact artifact ID required')
        subprocess.run(['gh', 'api', '--method', 'DELETE',
                        self.prefix + '/actions/artifacts/' + str(aid)], check=True)


def release_state(api):
    rows = api.pages('releases?per_page=100')
    stable = []
    usable = 0
    ordered = sorted([r for r in rows if not r['draft'] and not r['prerelease']],
                     key=lambda r: r['published_at'], reverse=True)
    for release in ordered:
        stable.append(release)
        names = {a['name'] for a in release['assets'] if a.get('state') == 'uploaded' and a['size'] > 0 and a.get('digest')}
        required = {'ARTIFACTS.json', 'SHA256SUMS.txt', 'Reprise-Skill.zip', 'reprise-workbuddy.zip'}
        if required <= names and any(n.endswith('.whl') for n in names) and any(n.endswith('.tar.gz') for n in names):
            usable += 1
        if usable == 2:
            break
    fingerprint = [(r['id'], r['tag_name'], r['target_commitish'],
                    [(a['id'], a['size'], a.get('digest')) for a in r['assets']]) for r in rows]
    shas = []
    for release in stable:
        obj = api.get('git/ref/tags/' + quote(release['tag_name'], safe=''))['object']
        seen = set()
        while obj['type'] == 'tag':
            if obj['sha'] in seen:
                raise ValueError('Cyclic tag')
            seen.add(obj['sha'])
            obj = api.get('git/tags/' + obj['sha'])['object']
        if obj['type'] != 'commit':
            raise ValueError('Release tag is not a commit')
        shas.append(obj['sha'])
    return {'releases': fingerprint, 'stableRefs': [(r['tag_name'], sha) for r, sha in zip(stable, shas)]}, shas


def build_snapshot(api, repository):
    meta = api.get()
    if meta['full_name'].lower() != repository.lower():
        raise ValueError('Repository identity mismatch')
    branch = meta['default_branch']
    head = api.get('commits/' + quote(branch, safe=''))['sha']
    artifacts = api.pages('actions/artifacts?per_page=100', 'artifacts')
    runs = api.pages('actions/workflows/ci.yml/runs?per_page=100', 'workflow_runs')
    fingerprint, release_shas = release_state(api)
    relevant = {a['workflow_run']['id'] for a in artifacts}
    jobs, pulls, covered = {}, {}, set()
    compare_cache, pulls_cache = {}, {}

    def is_covered(sha):
        if not sha:
            return False
        if sha not in compare_cache:
            compare_cache[sha] = api.get('compare/' + sha + '...' + head)['status'] in ('ahead', 'identical')
        return compare_cache[sha]

    for run in runs:
        if run['id'] not in relevant:
            continue
        if run['status'] == 'completed' and run['conclusion'] == 'success':
            jobs[run['id']] = api.pages('actions/runs/%s/jobs?filter=latest&per_page=100' % run['id'], 'jobs')
        if (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower():
            continue
        sha = run['head_sha']
        if sha not in pulls_cache:
            pulls_cache[sha] = api.pages('commits/' + sha + '/pulls?per_page=100')
        pulls[run['id']] = pulls_cache[sha]
        if run.get('event') == 'push' and run.get('head_branch') == branch and is_covered(sha):
            covered.add(sha)
        for pr in pulls[run['id']]:
            if pr.get('merged_at') and is_covered(pr.get('merge_commit_sha')):
                covered.add(pr['merge_commit_sha'])
    return {'repository': repository, 'default_branch': branch, 'main_sha': head,
            'artifacts': artifacts, 'runs': runs, 'jobs': jobs, 'pulls': pulls,
            'release_shas': release_shas, 'covered_commits': sorted(covered),
            'release_fingerprint': fingerprint}


def apply_plan(api, snapshot, plan, journal):
    if plan['state'] != 'ready':
        return []
    deleted = []
    for row in plan['delete']:
        # Revalidate both replacement and release identities before every destructive request.
        current = api.get('commits/' + quote(snapshot['default_branch'], safe=''))['sha']
        fingerprint, _ = release_state(api)
        if current != snapshot['main_sha'] or fingerprint != snapshot['release_fingerprint']:
            print('Cleanup stopped safely: main or releases changed.', flush=True)
            break
        replacement = api.get('actions/runs/' + str(plan['mainRun']))
        replacement_jobs = api.pages('actions/runs/%s/jobs?filter=latest&per_page=100' % plan['mainRun'], 'jobs')
        replacement_artifacts = api.pages('actions/runs/%s/artifacts?per_page=100' % plan['mainRun'], 'artifacts')
        expected = {a['id'] for a in plan['keep'] if a['reason'] == 'latest complete successful main'}
        if full_set(replacement, replacement_artifacts, replacement_jobs, snapshot['repository']) != expected:
            print('Cleanup stopped safely: replacement evidence changed.', flush=True)
            break
        live = api.get('actions/artifacts/' + str(row['id']))
        if (live['name'] != row['name'] or live['workflow_run']['id'] != row['runId'] or
                live['size_in_bytes'] != row['bytes'] or live.get('digest') != row['digest']):
            raise ValueError('Artifact identity changed before deletion')
        api.delete_artifact(row['id'])
        deleted.append(row)
        with Path(journal).open('a') as stream:
            stream.write(json.dumps(row) + '\n')
    return deleted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'), required=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    api = GitHub(args.repository or '')
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = build_snapshot(api, args.repository)
    plan = plan_cleanup(snapshot)
    (args.output / 'snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    deleted = apply_plan(api, snapshot, plan, args.output / 'deleted.jsonl') if args.apply else []
    result = {'state': plan['state'], 'apply': args.apply, 'mainRun': plan.get('mainRun'),
              'mainSha': snapshot['main_sha'], 'plannedDeletions': len(plan['delete']),
              'deleted': len(deleted), 'deletedBytes': sum(a['bytes'] for a in deleted),
              'kept': len(plan['keep'])}
    print('ARTIFACT_CLEANUP ' + json.dumps(result), flush=True)
    summary = ('## CI artifact lifecycle\n\n' + json.dumps(result, indent=2) +
               '\n\nOnly verified replacement artifacts are deleted. Releases, workflow runs, logs and local data are never deleted.\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
