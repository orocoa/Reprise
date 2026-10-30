"""Describe version operations from verified project, recipe and evidence data.

This is a read model, never execution approval. Running, restoring and deleting
still repeat their existing recipe, destination and transaction checks.
"""


def removal_effect(kind):
    return 'delete-saved' if kind == 'folder' else 'remove-local'


def version_actions(project, evidence):
    sha = project['revision']
    media = next(({'record': record['id'], 'index': index}
                  for record in evidence for index, item in enumerate(record.get('items', []))
                  if record.get('project_id') == project['id'] and item.get('sha') == sha
                  and item.get('kind') in ('image', 'video') and item.get('url')
                  and not item.get('missing') and not item.get('error')), None)
    recipe = project.get('recipe') or {}
    runnable = recipe.get('adapter') in ('static-web', 'command-web')
    if runnable:
        mode = 'run' if project.get('recipe_approved') else 'configure'
    elif project.get('kind') == 'archive':
        mode = 'saved' if media else 'recover'
    else:
        mode = 'configure'
    return {'schema': 1, 'project_id': project['id'], 'sha': sha,
            'preview': {'mode': mode, 'media': media if mode == 'saved' else None},
            'recovery': {'mode': 'copy'},
            'removal': {'effect': removal_effect(project.get('kind'))}}


def cleanup_actions(kind, has_environment):
    """Use the same effects for selection, plan review and execution receipts."""
    return {'choices': [
        {'id': 'all', 'effect': removal_effect(kind), 'enabled': True},
        {'id': 'environment', 'effect': 'clear-environment',
         'enabled': has_environment, 'reason': None if has_environment else 'no-managed-environment'}],
        'default': 'environment' if has_environment else 'all'}
