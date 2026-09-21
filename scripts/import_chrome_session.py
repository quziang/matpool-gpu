#!/usr/bin/env python3
"""Import only Matpool site session cookies after the user authorizes Chrome reuse."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import unquote

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', required=True, type=Path)
args = parser.parse_args()
folder = args.output_dir
folder.mkdir(mode=0o700, parents=True, exist_ok=True)
if folder.stat().st_mode & 0o077:
    raise SystemExit('Use a private output directory with mode 0700.')
base = Path.home() / 'Library/Application Support/Google/Chrome'
profile = json.loads((base/'Local State').read_text()).get('profile', {}).get('last_used', 'Default')
path = base/profile/'Cookies'
conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
rows = conn.execute("SELECT host_key,value,encrypted_value FROM cookies WHERE name=? AND host_key IN (?,?)", ('matpool_token','.matgo.cn','.matpool.com')).fetchall()
conn.close()
if not rows:
    raise SystemExit('No Matpool session cookies found in the active Chrome profile.')
# Read the OS-held Chrome encryption secret only for these two explicitly selected site cookies.
secret = subprocess.run(['security','find-generic-password','-w','-s','Chrome Safe Storage'], capture_output=True, check=True, timeout=20).stdout.rstrip(b'\n')
key = hashlib.pbkdf2_hmac('sha1', secret, b'saltysalt', 1003, 16)
lib = ctypes.CDLL('/usr/lib/system/libcommonCrypto.dylib')
lib.CCCrypt.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
lib.CCCrypt.restype = ctypes.c_int
for host, value, encrypted in rows:
    if not value:
        if not encrypted.startswith(b'v10'):
            raise SystemExit('Unsupported Chrome cookie encryption version; no secret printed.')
        payload = encrypted[3:]
        out = ctypes.create_string_buffer(len(payload)+16)
        moved = ctypes.c_size_t()
        status = lib.CCCrypt(1, 0, 1, key, len(key), b' '*16, payload, len(payload), out, len(out), ctypes.byref(moved))
        if status:
            raise SystemExit('Cookie decryption failed; no secret printed.')
        plain = out.raw[:moved.value]
        prefix = hashlib.sha256(host.encode()).digest()
        if not plain.startswith(prefix):
            raise SystemExit('Cookie host binding did not match; no secret saved.')
        value = plain[32:].decode('utf-8')
    value = unquote(value)
    if not value.startswith('Bearer '):
        raise SystemExit('Unexpected site authentication format; no secret printed.')
    name = 'matgo-web.token' if host == '.matgo.cn' else 'matpool-web.token'
    fd = os.open(folder/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as f: f.write(value.removeprefix('Bearer ') + '\n')
    print('Saved only Matpool site credential:', name, '(0600)')
