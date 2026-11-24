"""Public, fail-closed configuration for optional manual audience measurement."""

import os
import re
from urllib.parse import urlsplit
from uuid import UUID


def _hostname(value: str) -> bool:
    return bool(len(value) <= 253 and re.fullmatch(
        r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
        r'[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?', value
    ))


def audience_options(environ=None):
    """Only public tracker values leave this function; malformed config disables it."""
    env = os.environ if environ is None else environ
    if env.get('BRT_AUDIENCE_ENABLED') != '1':
        return {'enabled': False}
    script = env.get('BRT_AUDIENCE_SCRIPT_URL', '')
    website = env.get('BRT_AUDIENCE_WEBSITE_ID', '')
    hostname = env.get('BRT_AUDIENCE_HOSTNAME', '').lower()
    try:
        parsed = urlsplit(script)
        port = parsed.port
        if (any(ord(char) <= 32 or ord(char) == 127 for char in script)
                or parsed.scheme != 'https' or not _hostname(parsed.hostname or '')
                or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?', parsed.netloc)
                or parsed.username is not None or parsed.password is not None
                or '?' in script or '#' in script
                or (port is not None and not 1 <= port <= 65535)
                or not re.fullmatch(r'/[A-Za-z0-9._/-]+\.js', parsed.path)
                or not _hostname(hostname)):
            return {'enabled': False}
        website = str(UUID(website))
    except (ValueError, TypeError, AttributeError):
        return {'enabled': False}
    return {'enabled': True, 'script_url': script, 'website_id': website, 'hostname': hostname}


def audience_origin(options):
    if not options.get('enabled'):
        return ''
    parsed = urlsplit(options['script_url'])
    port = f':{parsed.port}' if parsed.port is not None else ''
    return f'{parsed.scheme}://{parsed.hostname}{port}'
