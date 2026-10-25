"""The visual-draft workflow, using the existing storage and capture services.

This layer describes user tasks. Repositories own saved bytes; evidence owns
media identity; runtimes own execution. No alternate version store lives here.
"""
from .quick_preview import prepare_quick_preview
from .vite_preview import prepare_vite_preview


def visual_history(app, identifier):
    """One read of evidence for a project, indexed by its exact recorded version."""
    app.projects.record(identifier)
    images = {}
    for record in app.evidence.list(identifier):
        for item in record.get('items', []):
            side = 'base' if item.get('side') in ('before', 'base') else 'target'
            expected = record.get('base') if side == 'base' else record.get('sha')
            sha = item.get('sha') or expected
            if not sha or sha != expected or item.get('missing') or item.get('error'):
                continue
            if not item.get('url') or not item.get('media_type', '').startswith('image/'):
                continue
            # A newer valid capture wins. Never borrow another version's image.
            date = record.get('created_at', '')
            status = record.get('status', 'unknown')
            complete = status == 'complete' and not record.get('errors')
            priority = (complete, date)
            prior = images.get(sha)
            if prior is None or priority > (prior['complete'], prior['created_at']):
                images[sha] = {'sha': sha, 'url': item['url'], 'title': item.get('title', ''),
                               'created_at': date, 'source': record.get('source'),
                               'record_id': record['id'], 'capture_id': item.get('capture_id'),
                               'status': status, 'complete': complete,
                               'verification': record.get('verification'),
                               'warnings': record.get('warnings', []), 'errors': record.get('errors', [])}
    return {'project_id': identifier, 'images': images}


def plan_draft_preview(app, identifier, sha, *, root=None):
    repository = app.projects.repository(identifier)
    plan = prepare_vite_preview(repository, sha, root=root)
    if plan['reason'] == 'no-supported-vite-project':
        plan = prepare_quick_preview(repository, sha, root=root)
    existing = app.projects.record(identifier).get('version_recipes', {}).get(sha, {}).get('recipe')
    if existing is not None and (existing != plan.get('recipe') or
                                  existing.get('adapter') == 'command-web'):
        return {**plan, 'status': 'needs-configuration', 'reason': 'existing-settings',
                'recipe': None}
    return plan


def capture_draft(app, identifier, sha, *, root=None, cancel=None):
    """Called only after the user explicitly asks to save a static webpage image."""
    repository = app.projects.repository(identifier)
    plan = plan_draft_preview(app, identifier, sha, root=root)
    if plan['status'] != 'ready':
        return {'status': plan['status'], 'sha': sha, 'plan': plan}
    existing = app.projects.record(identifier).get('version_recipes', {}).get(sha, {}).get('recipe')
    if existing is None:
        app.projects.save_recipe(identifier, plan['recipe'], sha)
    result = app.captures.capture(repository, identifier, sha, plan['recipe'],
                                  approved=True, cancel=cancel)
    return app.evidence.public(result)


def queue_capture(app, identifier, body):
    sha, root = body.get('sha'), body.get('root')
    # Validate the immutable identity and entry before a job is accepted.
    plan = plan_draft_preview(app, identifier, sha, root=root)
    if plan['status'] != 'ready':
        raise ValueError('此版本需要先选择网页入口或补充运行配置。')
    return app.jobs.submit(identifier, 'capture',
        lambda cancel: capture_draft(app, identifier, sha, root=root, cancel=cancel),
        request={'sha': sha, 'quick_preview': True, 'root': root}, cancellable=True)


def save_draft(app, identifier, title, preference, cancel):
    """Save is durable before optional capture. Capture failure is a separate result.

    ``quick`` is consent for a freshly detected local static webpage only.
    ``auto`` is the pre-existing explicit project template, frozen before queueing.
    Other modes never start a runtime or browser.
    """
    from .cancellation import check, Cancelled
    result = app.projects.snapshot(identifier, title, cancel)
    mode = preference.get('mode', 'remind')
    result.update(saved=True, preview={'mode': mode, 'sha': result['sha'],
                                      'status': 'not-requested'})
    preview = result['preview']
    if mode not in ('quick', 'auto'):
        preview['status'] = 'optional' if mode in ('manual', 'remind') else 'not-requested'
        return result
    try:
        check(cancel)
        if mode == 'quick' or preference.get('pending_recipe'):
            evidence = capture_draft(app, identifier, result['sha'], cancel=cancel)
        else:
            recipe = preference['recipe']
            app.projects.save_recipe(identifier, recipe, result['sha'])
            evidence = app.evidence.public(app.captures.capture(
                app.projects.repository(identifier), identifier, result['sha'], recipe,
                approved=True, cancel=cancel))
        preview['status'] = evidence['status']
        if 'plan' in evidence:
            preview['plan'] = evidence['plan']
        else:
            preview['evidence'] = evidence
    except Exception as error:
        preview.update(status='cancelled' if isinstance(error, Cancelled) else 'failed',
                       error=str(error))
    return result
