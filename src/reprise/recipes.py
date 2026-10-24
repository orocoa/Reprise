"""Strict, deterministic preview recipes. Reading one never executes code."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit


ADAPTERS = ('static-web', 'command-web', 'manual')
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError('%s must be an integer between %s and %s' % (name, low, high))
    return value


def _text(value, name, limit=2048, empty=False):
    if not isinstance(value, str) or '\x00' in value or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('%s must be valid text (maximum %s characters)' % (name, limit))
    return value


def _route(value, name):
    value = _text(value, name)
    parsed = urlsplit(value)
    if not value.startswith('/') or value.startswith('//') or parsed.scheme or parsed.netloc or '\\' in value:
        raise ValueError('%s must be a local route beginning with /' % name)
    return value


def _argv(value, name):
    if not isinstance(value, list) or not value or len(value) > 100:
        raise ValueError('%s must be a nonempty argv array' % name)
    result = [_text(part, name, 8192, empty=index > 0) for index, part in enumerate(value)]
    # Commands are never passed to a shell. Explicit shell interpreters remain user-approved code.
    return result


def _environment(value):
    if not isinstance(value, dict) or set(value) - {'outputs', 'inputs', 'tools'}:
        raise ValueError('environment supports outputs, inputs and tools')
    result = {}
    for field in ('outputs', 'inputs'):
        paths = value.get(field)
        if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
            raise ValueError('environment.%s requires 1–16 relative paths' % field)
        normalized = []
        for path in paths:
            path = _text(path, 'environment.' + field, 1024)
            parsed = PurePosixPath(path)
            if (path.startswith('/') or '\\' in path or ':' in path or
                    any(part == '..' or part.casefold() == '.git' for part in parsed.parts) or str(parsed) == '.'):
                raise ValueError('Environment paths must remain inside the historical workspace')
            normalized.append(str(parsed))
        result[field] = sorted(set(normalized))
    for output in result['outputs']:
        if any(other != output and (other.startswith(output + '/') or output.startswith(other + '/'))
               for other in result['outputs']):
            raise ValueError('Environment outputs must not overlap')
        if any(path == output or path.startswith(output + '/') for path in result['inputs']):
            raise ValueError('Environment inputs cannot be inside generated outputs')
    tools = value.get('tools')
    if not isinstance(tools, list) or not 1 <= len(tools) <= 8:
        raise ValueError('environment.tools requires 1–8 Node/Python tool executable names or absolute paths')
    normalized = []
    for tool in tools:
        tool = _text(tool, 'environment.tools', 4096)
        basename = PurePosixPath(tool).name
        if (not re.fullmatch(r'(?:node|npm|pnpm|yarn|python(?:[0-9]+(?:\.[0-9]+)?)?)', basename)
                or ('/' in tool and not tool.startswith('/')) or '\\' in tool):
            raise ValueError('Environment tools must name a Node/Python executable; probes only run --version')
        normalized.append(tool)
    result['tools'] = sorted(set(normalized))
    return result


def validate_recipe(value):
    if not isinstance(value, dict):
        raise ValueError('Recipe must be an object')
    allowed = {'schema', 'adapter', 'root', 'commands', 'readiness', 'captures', 'network', 'environment'}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError('Unknown recipe fields: %s' % ', '.join(sorted(unknown)))
    if value.get('schema', 1) != 1 or isinstance(value.get('schema'), bool):
        raise ValueError('Only recipe schema 1 is supported')
    adapter = value.get('adapter')
    if adapter not in ADAPTERS:
        raise ValueError('Adapter must be static-web, command-web or manual')
    root = _text(value.get('root', '.'), 'root', 1024)
    if '\\' in root or root.startswith('/') or '..' in PurePosixPath(root).parts or ':' in root:
        raise ValueError('Recipe root must stay inside the version snapshot')
    root = str(PurePosixPath(root))
    commands = value.get('commands', {})
    if not isinstance(commands, dict) or set(commands) - {'install', 'build', 'start'}:
        raise ValueError('commands supports only install, build and start')
    normalized_commands = {}
    for phase in ('install', 'build'):
        if phase in commands:
            if not isinstance(commands[phase], list) or len(commands[phase]) > 20:
                raise ValueError('%s must be an array of argv arrays' % phase)
            normalized_commands[phase] = [_argv(cmd, phase) for cmd in commands[phase]]
    if 'start' in commands:
        normalized_commands['start'] = _argv(commands['start'], 'start')
    if adapter == 'command-web' and not normalized_commands.get('start'):
        raise ValueError('command-web requires commands.start as an argv array')
    if adapter != 'command-web' and normalized_commands:
        raise ValueError('Only command-web may execute commands')
    readiness = value.get('readiness', {})
    if not isinstance(readiness, dict) or set(readiness) - {'path', 'selector', 'timeout_ms'}:
        raise ValueError('readiness supports path, selector and timeout_ms')
    ready = {'path': _route(readiness.get('path', '/'), 'readiness.path'),
             'timeout_ms': _integer(readiness.get('timeout_ms', 15000), 'readiness.timeout_ms', 100, 300000)}
    if readiness.get('selector') is not None:
        ready['selector'] = _text(readiness['selector'], 'readiness.selector')
    network = value.get('network', 'local')
    if network not in ('local', 'allow'):
        raise ValueError('network must be local or allow')
    captures = value.get('captures', [] if adapter == 'manual' else [{'id': 'main'}])
    if not isinstance(captures, list) or len(captures) > 30:
        raise ValueError('captures must be an array containing at most 30 scenarios')
    if adapter != 'manual' and not captures:
        raise ValueError('Browser recipes require at least one capture scenario')
    result, ids = [], set()
    for index, capture in enumerate(captures):
        if not isinstance(capture, dict) or set(capture) - {'id', 'route', 'viewport', 'full_page', 'wait_for', 'steps', 'record', 'record_ms'}:
            raise ValueError('Invalid capture scenario fields')
        cid = capture.get('id', 'capture-%s' % (index + 1))
        if not isinstance(cid, str) or not _ID.fullmatch(cid) or cid in ids:
            raise ValueError('Each capture needs a unique safe id (letters, numbers, ., _ or -)')
        ids.add(cid)
        viewport = capture.get('viewport', {})
        if not isinstance(viewport, dict) or set(viewport) - {'width', 'height', 'scale'}:
            raise ValueError('viewport supports width, height and scale')
        scale = viewport.get('scale', 2)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not 1 <= scale <= 3:
            raise ValueError('viewport.scale must be between 1 and 3')
        vp = {'width': _integer(viewport.get('width', 1440), 'viewport.width', 240, 3840),
              'height': _integer(viewport.get('height', 900), 'viewport.height', 240, 2160), 'scale': scale}
        for flag in ('full_page', 'record'):
            if flag in capture and not isinstance(capture[flag], bool):
                raise ValueError('%s must be boolean' % flag)
        scenario = {'id': cid, 'route': _route(capture.get('route', ready['path']), 'route'),
                    'viewport': vp, 'full_page': capture.get('full_page', False),
                    'record': capture.get('record', False), 'steps': []}
        if 'record_ms' in capture:
            scenario['record_ms'] = _integer(capture['record_ms'], 'record_ms', 0, 60000)
        if capture.get('wait_for') is not None:
            scenario['wait_for'] = _text(capture['wait_for'], 'wait_for')
        steps = capture.get('steps', [])
        if not isinstance(steps, list) or len(steps) > 100:
            raise ValueError('steps must contain at most 100 actions')
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError('Each step must be an object')
            action = step.get('action')
            fields = {'click': {'action', 'selector'}, 'press': {'action', 'selector', 'key'},
                      'fill': {'action', 'selector', 'value'}, 'wait': {'action', 'ms'}}
            if action not in fields or set(step) - fields[action]:
                raise ValueError('Steps support only click, press, fill and wait')
            item = {'action': action}
            if action in ('click', 'fill') or (action == 'press' and 'selector' in step):
                item['selector'] = _text(step.get('selector'), 'step.selector')
            if action == 'press':
                item['key'] = _text(step.get('key'), 'step.key', 100)
            if action == 'fill':
                item['value'] = _text(step.get('value'), 'step.value', 10000, empty=True)
            if action == 'wait':
                item['ms'] = _integer(step.get('ms', 500), 'step.ms', 0, 60000)
            scenario['steps'].append(item)
        result.append(scenario)
    recipe = {'schema': 1, 'adapter': adapter, 'root': root, 'commands': normalized_commands,
              'readiness': ready, 'captures': result, 'network': network}
    if 'environment' in value:
        if adapter != 'command-web':
            raise ValueError('Only command-web supports a managed environment')
        recipe['environment'] = _environment(value['environment'])
    return recipe


def recipe_hash(recipe):
    normalized = validate_recipe(recipe)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
