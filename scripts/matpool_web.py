#!/usr/bin/env python3
"""Direct HTTPS client for Matpool's website API (requires website session token)."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from matpool_api import InputError, NoRedirect, positive
from matpool_auth import CredentialError, load_token

BASE = 'https://matgo.cn/api'
RENT_FIELDS = {'resource_pool_id', 'image_id', 'hardware_qty', 'machine_category',
               'vnc_switcher', 'auto_password', 'c', 'public_key', 'cmd', 'ports',
               'tmux_support', 'vnc_support'}


def request(method, path, token, query=None, body=None, timeout=25):
    if not token or any(c in token for c in '\r\n'):
        raise InputError('A website session token is required; PaaS tokens are separate')
    url = BASE + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json',
               'User-Agent': 'matpool-gpu-skill/1'}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        response = urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status, raw = response.code, response.read()
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise InputError(f'HTTP {status}: non-JSON response; no automatic retry') from None
    if not isinstance(result, dict):
        raise InputError('Expected JSON object')
    return status, result


def summary(result):
    # Connection details, credentials, startup commands and account data stay private.
    out = {k: result[k] for k in ('code', 'pagination') if k in result}
    if isinstance(result.get('node'), dict):
        out['created_node_id'] = result['node'].get('id')
    if 'images' in result:
        out['images'] = [{k: x.get(k) for k in ('id', 'alias', 'cached', 'public', 'status')}
                         for x in result['images']]
    nodes = result.get('userNodes', [])
    if result.get('userNode'):
        nodes = [result['userNode']]
    if nodes:
        out['node_count'] = len(nodes)
        out['nodes'] = [dict(id=x.get('node', {}).get('id'), displayID=x.get('displayID'),
                             status=x.get('status'), state=x.get('state', {}).get('status'),
                             createTime=x.get('node', {}).get('createTime'),
                             releaseTime=x.get('node', {}).get('releaseTime'))
                        for x in nodes[:20]]
    out['response_keys'] = list(result)
    return out


def prepare_rent(body):
    if not isinstance(body, dict) or set(body) - RENT_FIELDS:
        raise InputError('Rent body contains unsupported fields')
    if body.get('machine_category') != 0 or type(body.get('machine_category')) is not int:
        raise InputError('Only verified GPU category 0 is supported')
    for k in ('image_id', 'hardware_qty'):
        if type(body.get(k)) is not int or body[k] < 1:
            raise InputError(f'{k} must be a positive integer')
    if not isinstance(body.get('resource_pool_id'), str) or not body['resource_pool_id']:
        raise InputError('Use a resource_pool_id from fresh inventory')
    if 'cmd' in body and (not isinstance(body['cmd'], str) or len(body['cmd'].encode('utf-8')) > 1024):
        raise InputError('Keep startup cmd within 1024 UTF-8 bytes; transfer longer scripts through SSH')
    if 'ports' in body:
        ports = json.loads(body['ports'])
        if not isinstance(ports, list) or any(
            not isinstance(p, dict) or set(p) != {'srcPort', 'protocol'}
            or type(p['srcPort']) is not int or not 1 <= p['srcPort'] <= 65535
            or type(p['protocol']) is not int or p['protocol'] not in (1, 2, 3, 4)
            for p in ports
        ):
            raise InputError('ports must encode srcPort/protocol objects')
    return body


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file', type=Path, help='Override environment or initialized web credential')
    p.add_argument('--output', type=Path, help='New private file for full response')
    sub = p.add_subparsers(dest='command', required=True)
    images = sub.add_parser('images')
    images.add_argument('--pool', required=True)
    images.add_argument('--keyword')
    images.add_argument('--page', type=positive, default=1)
    ls = sub.add_parser('nodes')
    ls.add_argument('--page', type=positive, default=1)
    bill = sub.add_parser('bill')
    bill.add_argument('request_id', help='Verified displayID, not internal numeric node ID')
    for name in ('get', 'release'):
        q = sub.add_parser(name)
        q.add_argument('id', type=positive)
        if name == 'release':
            q.add_argument('--execute', action='store_true')
    rent = sub.add_parser('rent')
    rent.add_argument('--file', type=Path, required=True)
    rent.add_argument('--execute', action='store_true')
    args = p.parse_args(argv)
    sink = None
    try:
        method, path, query, body = 'GET', '/node', {}, None
        if args.command == 'images':
            path = '/images'
            query = dict(resource_pool_id=args.pool, machine_category=0,
                         page=args.page, per_page=100)
            if args.keyword:
                query['keywords'] = json.dumps([args.keyword])
        elif args.command == 'nodes':
            path = '/nodes'
            query = dict(page=args.page, per_page=100, order='false')
        elif args.command == 'bill':
            path, query = '/node/bill', {'request_id': args.request_id}
        elif args.command == 'get':
            query = {'id': args.id}
        elif args.command == 'release':
            method, body = 'DELETE', {'id': args.id}
        else:
            method, body = 'POST', prepare_rent(json.loads(args.file.read_text()))
        if args.command in ('rent', 'release') and not args.execute:
            visible = {k: ('[REDACTED]' if k in ('cmd', 'public_key') else v)
                       for k, v in body.items()}
            print(json.dumps(dict(preview=True, method=method, url=BASE+path, body=visible), indent=2))
            return 0
        token = load_token('web', args.token_file)
        if args.output:
            sink = os.fdopen(os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w')
        status, result = request(method, path, token, query, body)
        if sink:
            json.dump(dict(http_status=status, response=result), sink, ensure_ascii=False, indent=2)
        print(json.dumps(dict(http_status=status, response=summary(result)), ensure_ascii=False, indent=2))
        return 0 if 200 <= status < 300 and type(result.get('code')) is int and result['code'] == 0 else 1
    except (OSError, ValueError, urllib.error.URLError) as error:
        msg = str(error) if isinstance(error, (InputError, CredentialError)) else type(error).__name__
        print(f'Failed: {msg}. No automatic retry; check nodes before repeating rent.', file=sys.stderr)
        return 2
    finally:
        if sink:
            sink.close()


if __name__ == '__main__':
    sys.exit(main())
