#!/usr/bin/env python3
"""Initialize local Matpool credentials and verify them with read-only requests."""
import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import warnings

SERVICES = {
    'web': ('MATPOOL_WEB_TOKEN', 'matgo-web.token'),
    'paas': ('MATPOOL_PAAS_TOKEN', 'paas.token'),
}


class CredentialError(ValueError):
    """Only fixed, credential-free messages may be used here."""


def config_directory(folder=None):
    return Path(folder or os.environ.get('MATPOOL_CONFIG_DIR')
                or Path.home() / '.config' / 'matpool-gpu').expanduser()


def token_path(service, folder=None):
    return config_directory(folder) / SERVICES[service][1]


def normalize_token(value):
    value = value.strip()
    if value.startswith('Bearer '):
        value = value[7:]
    if not value or value == 'Bearer' or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise CredentialError('Token must be nonempty ASCII without embedded whitespace.')
    return value


def credential_source(service, explicit_file=None, folder=None):
    """Keep explicit file > environment > initialized file precedence."""
    if explicit_file is not None:
        return 'file', Path(explicit_file).expanduser()
    variable = SERVICES[service][0]
    if variable in os.environ:
        return 'environment', variable
    return 'initialized_file', token_path(service, folder)


def load_token(service, explicit_file=None, folder=None):
    source, location = credential_source(service, explicit_file, folder)
    if source == 'environment':
        value = os.environ[location]
    else:
        if source == 'initialized_file' and not location.exists():
            raise CredentialError('No credential configured. Run matpool_auth.py init --service '
                                  + service + ', set its environment variable, or use --token-file.')
        value = location.read_text(encoding='utf-8')
    # Never fall back to a different credential after an explicit source fails.
    return normalize_token(value)


def save_token(service, value, folder=None, replace=False):
    value = normalize_token(value)
    directory = config_directory(folder)
    if directory.is_symlink():
        raise CredentialError('Credential directory must not be a symbolic link.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077
            or (hasattr(os, 'getuid') and info.st_uid != os.getuid())):
        raise CredentialError('Use a credential directory owned by you with mode 0700.')
    destination = token_path(service, directory)
    if destination.is_symlink():
        raise CredentialError('Credential file must not be a symbolic link.')
    if destination.exists() and not replace:
        raise CredentialError('Credential already exists. Use --replace to renew it intentionally.')
    # Create in the same private directory, then publish atomically. No token in argv/logs.
    fd, temporary = tempfile.mkstemp(prefix='.token-', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(value + '\n')
        if replace:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)  # Refuse overwrite, including a concurrent init.
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def local_status(service, folder=None):
    source, location = credential_source(service, folder=folder)
    configured = source == 'environment' or location.exists()
    out = dict(service=service, configured=configured, source=source,
               location=str(location), verified=False)
    if configured:
        try:
            load_token(service, folder=folder)
            out['local_format_valid'] = True
        except (OSError, ValueError):
            out['local_format_valid'] = False
    return out


def verify(service, token):
    # Import lazily: the API clients also use this module to load credentials.
    if service == 'web':
        from matpool_web import request
        status, result = request('GET', '/nodes', token,
                                 query={'page': 1, 'per_page': 1, 'order': 'false'})
    else:
        from matpool_api import request
        status, result = request('GET', '/v1/job/stats', {}, None, token, 25)
    code = result.get('code')
    valid = 200 <= status < 300 and type(code) is int and code == 0
    # Server messages and account data can contain secrets. Only emit these fields.
    return dict(service=service, verified=valid, http_status=status,
                code=code if type(code) is int else None)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config-dir', type=Path,
                   help='Credential directory (default: MATPOOL_CONFIG_DIR or ~/.config/matpool-gpu)')
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Save one credential locally; no network or browser access')
    init.add_argument('--service', choices=SERVICES, required=True)
    sources = init.add_mutually_exclusive_group()
    sources.add_argument('--from-env', action='store_true', help='Read the selected service environment variable')
    sources.add_argument('--token-file', type=Path, help='Import from an existing private file')
    init.add_argument('--replace', action='store_true', help='Replace this service credential for renewal')
    status = sub.add_parser('status', help='Show credential sources, never values; no network')
    status.add_argument('--service', choices=SERVICES)
    check = sub.add_parser('check', help='Verify one service via a read-only HTTPS request')
    check.add_argument('--service', choices=SERVICES, required=True)
    check.add_argument('--token-file', type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'status':
            states = [local_status(s, args.config_dir) for s in
                      ([args.service] if args.service else SERVICES)]
            print(json.dumps({'credentials': states}, ensure_ascii=False, indent=2))
            return 2 if any(s.get('local_format_valid') is False for s in states) else 0
        if args.command == 'check':
            token = load_token(args.service, args.token_file, args.config_dir)
            result = verify(args.service, token)
            source, location = credential_source(args.service, args.token_file, args.config_dir)
            result.update(source=source, location=str(location))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['verified'] else 1
        if args.token_file:
            value = args.token_file.expanduser().read_text(encoding='utf-8')
        elif args.from_env:
            value = os.environ.get(SERVICES[args.service][0], '')
        else:
            if not sys.stdin.isatty():
                raise CredentialError('Run init in your own interactive terminal, or use --from-env/--token-file; '
                                      'do not paste credentials into chat.')
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                value = getpass.getpass(args.service + ' Token (hidden input): ')
        destination = save_token(args.service, value, args.config_dir, args.replace)
        source, location = credential_source(args.service, folder=args.config_dir)
        print(json.dumps(dict(service=args.service, saved=True, path=str(destination),
                              verified=False, active_source=source, active_location=str(location)), indent=2))
        if source == 'environment':
            print('Environment variable takes precedence; unset it to use the saved file.', file=sys.stderr)
        return 0
    except (OSError, ValueError, EOFError, getpass.GetPassWarning) as error:
        message = str(error) if isinstance(error, CredentialError) else 'Credential operation failed; no secret printed.'
        print('Error: ' + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Cancelled; no secret printed.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
