"""Inspectable local processing contract, shared by the UI and the CLI."""
from pathlib import Path


def describe(directory, projects, ai):
    root = Path(directory).resolve()
    return {
        'schema': 1, 'storage': str(root), 'encrypted': False,
        'scope': 'explicitly_added_projects_only', 'background_watcher': False,
        'local_operations': ['snapshot', 'fingerprint', 'deduplicate', 'compare', 'restore', 'organize', 'version-delete-plan', 'version-delete', 'environment-release'],
        'local_operations_use_ai': False, 'local_operations_upload': False,
        'telemetry': False,
        'stored_metadata': ['relative paths', 'file type', 'size', 'mode', 'mtime/ctime',
                            'device/inode signatures', 'content hashes', 'version references',
                            'exclusions', 'verification receipts'],
        'stored_content': 'Versioned file bytes are stored locally; the index is not only hashes.',
        'semantic_analysis': False,
        'ai': {'enabled': ai.state()['enabled'], 'automatic_content_processing': False,
               'boundary': 'Explicit AI suggestions can send paths, commit information and bounded build manifests to the configured provider.'},
        'agent_boundary': 'When used through an AI agent, command outputs and opened files may enter that agent context. Agent provider policies apply separately.',
        'retention': 'Saved versions, indexes, receipts and recovery outputs remain until explicitly managed by the user. Excluding a path later does not erase older saved versions.',
        'deletion_scope': 'Explicit reviewed plans remove selected managed snapshots and unreferenced objects; sources, evidence, recovery copies and diagnostic objects stay. Environment release removes only registered, verified generated outputs.',
        'runtime_boundary': 'Approved install/build/run commands are local code, not a sandbox; they can use network and host permissions. The browser capture network setting does not sandbox package-manager commands.',
        'projects': [{k: p[k] for k in ('id', 'name', 'kind', 'path', 'exclusions') if k in p}
                     for p in projects.records()],
    }
