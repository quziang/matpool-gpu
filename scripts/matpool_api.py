#!/usr/bin/env python3
"""Small HTTPS client for the documented Matpool PaaS job API."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from matpool_auth import CredentialError, load_token

BASE_URL = 'https://paas.matpool.com'
PRIVATE_KEYS = {'creds', 'password', 'token', 'authorization', 'sshauths',
                'envs', 'cmd', 'urls', 'extradata', 'secret', 'access_token'}
FIELDS = {'spec', 'agent_domain', 'from_image_id', 'from_snapshot_id',
          'cmd', 'remark', 'envs', 'domain', 'ports'}


class InputError(ValueError):
    """An error message known not to contain caller secrets."""


def redact(value, token=''):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k.lower() in PRIVATE_KEYS else redact(v, token)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, token) for v in value]
    if isinstance(value, str) and token:
        return value.replace(token, '[REDACTED]')
    return value


def positive(value):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('Expected a positive integer') from None
    if result <= 0:
        raise argparse.ArgumentTypeError('Expected a positive integer')
    return result


def prepare_fields(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise InputError('Job must be an object containing only documented fields')
    fields = dict(data)
    if type(fields.get('agent_domain')) is not int or fields['agent_domain'] < 0:
        raise InputError('agent_domain must be a verified nonnegative integer')
    selected = [k for k in ('from_image_id', 'from_snapshot_id') if k in fields]
    if len(selected) != 1 or type(fields[selected[0]]) is not int or fields[selected[0]] <= 0:
        raise InputError('Supply exactly one positive image or snapshot ID')
    for key in ('cmd', 'remark'):
        if not isinstance(fields.get(key), str) or not fields[key].strip():
            raise InputError(f'{key} must be an explicit nonempty string')
    for key in ('envs', 'domain'):
        if key in fields and not isinstance(fields[key], str):
            raise InputError(f'{key} must be a string')
    if fields.get('domain', 'all') not in {'all', 'offical', 'others'}:
        raise InputError('domain must be all, offical, or others')
    spec = fields.get('spec')
    if isinstance(spec, str):
        spec = json.loads(spec)
    if (not isinstance(spec, dict) or set(spec) != {'gpuName'}
            or not isinstance(spec['gpuName'], str) or not spec['gpuName'].strip()):
        raise InputError('spec must contain a nonempty gpuName; other keys are not documented')
    fields['spec'] = json.dumps(spec, ensure_ascii=False)
    if 'ports' in fields:
        ports = fields['ports']
        if isinstance(ports, str):
            ports = json.loads(ports)
        if not isinstance(ports, list):
            raise InputError('ports must be a JSON array')
        for entry in ports:
            if (not isinstance(entry, dict) or set(entry) != {'port', 'protocol'}
                    or type(entry['port']) is not int or not 1 <= entry['port'] <= 65535
                    or type(entry['protocol']) is not int or entry['protocol'] not in (1, 2, 3, 4)):
                raise InputError('Each port requires port 1..65535 and protocol 1..4')
        fields['ports'] = json.dumps(ports)
    return {k: str(v) for k, v in fields.items()}


def multipart(fields):
    boundary = 'matpool-' + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                      f'\r\n\r\n{value}\r\n').encode('utf-8'))
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer credential to another host or downgrade transport.
        return None


def request(method, path, query, fields, token, timeout):
    url = BASE_URL + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    headers = {'Accept': 'application/json', 'User-Agent': 'matpool-gpu-skill/1'}
    if token:
        if '\r' in token or '\n' in token:
            raise InputError('Token must not contain newlines')
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if fields is not None:
        body, headers['Content-Type'] = multipart(fields)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.code
        raw = response.read()
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise InputError(f'HTTP {status}: response is not JSON; request not retried') from None
    if not isinstance(result, dict):
        raise InputError(f'HTTP {status}: expected a JSON object; request not retried')
    return status, result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file', type=Path, help='Override environment or initialized PaaS credential')
    p.add_argument('--output', type=Path, help='Create a 0600 file with full response; never overwrite')
    p.add_argument('--timeout', type=float, default=30)
    subs = p.add_subparsers(dest='command', required=True)
    subs.add_parser('probe', help='Unauthenticated read-only HTTPS probe')
    subs.add_parser('stats', help='Query task counts and status lists')
    ls = subs.add_parser('list', help='Query one page of task details')
    ls.add_argument('--page', type=positive, default=1)
    ls.add_argument('--per-page', type=positive, default=20)
    ls.add_argument('--order', choices=['true', 'false'], default='false')
    get = subs.add_parser('get', help='Query task by internal numeric ID')
    get.add_argument('id', type=positive)
    create = subs.add_parser('create', help='Preview or submit a multipart job')
    create.add_argument('--file', type=Path, required=True)
    create.add_argument('--execute', action='store_true')
    cancel = subs.add_parser('cancel', help='Preview or cancel one task')
    cancel.add_argument('id', type=positive)
    cancel.add_argument('--execute', action='store_true')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    token = ''
    sink = None
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise InputError('timeout must be finite and positive')
        fields, query, method, path = None, {}, 'GET', '/v1/job'
        if args.command in {'probe', 'stats'}:
            path += '/stats'
        elif args.command == 'list':
            path += '/jobs'
            query = {'page': args.page, 'per_page': args.per_page, 'order': args.order}
        elif args.command in {'get', 'cancel'}:
            query = {'id': args.id}
            if args.command == 'cancel':
                method = 'DELETE'
        elif args.command == 'create':
            method = 'POST'
            fields = prepare_fields(json.loads(args.file.read_text(encoding='utf-8')))
        if args.command in {'create', 'cancel'} and not args.execute:
            print(json.dumps({'preview': True, 'method': method, 'url': BASE_URL + path,
                              'query': query, 'fields': redact(fields)}, ensure_ascii=False, indent=2))
            return 0
        if args.command != 'probe':
            token = load_token('paas', args.token_file)
        # Reserve output before a mutation so an invalid path cannot cause lost results.
        if args.output:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            sink = os.fdopen(fd, 'w', encoding='utf-8')
        status, result = request(method, path, query, fields, token, args.timeout)
        if sink:
            json.dump({'http_status': status, 'response': result}, sink, ensure_ascii=False, indent=2)
            sink.write('\n')
        print(json.dumps({'http_status': status, 'response': redact(result, token)},
                         ensure_ascii=False, indent=2))
        return 0 if 200 <= status < 300 and type(result.get('code')) is int and result['code'] == 0 else 1
    except (OSError, ValueError, urllib.error.URLError) as error:
        # Do not print exception bodies: a malformed header or network error can include secrets.
        message = str(error) if isinstance(error, (InputError, CredentialError)) else 'Request failed or input invalid'
        print(f'Error ({type(error).__name__}): {message}; no automatic retry.', file=sys.stderr)
        if args.command in {'create', 'cancel'} and args.execute:
            print('If a request reached the service, query task state before retrying.', file=sys.stderr)
        return 2
    finally:
        if sink:
            sink.close()


if __name__ == '__main__':
    sys.exit(main())
