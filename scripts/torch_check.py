#!/usr/bin/env python3
"""Find an image's PyTorch interpreter and verify CUDA matmul; run on the GPU node."""
import argparse
import glob
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

CHECK = r'''
import json, sys, torch
r = dict(python=sys.executable, python_version=sys.version.split()[0], torch_version=torch.__version__,
         torch_file=torch.__file__, cuda_runtime=torch.version.cuda, cuda_available=torch.cuda.is_available())
try:
 assert r['cuda_available'], 'CUDA is unavailable'
 torch.manual_seed(7)
 a = torch.randn(512, 512, device='cuda', dtype=torch.float32)
 b = torch.randn(512, 512, device='cuda', dtype=torch.float32)
 c = a @ b
 torch.cuda.synchronize()
 reference = a.cpu() @ b.cpu()
 error = (c.cpu() - reference).abs().max().item()
 ok = torch.allclose(c.cpu(), reference, rtol=1e-4, atol=1e-4)
 r.update(device=torch.cuda.get_device_name(0), result_device=str(c.device), shape=list(c.shape),
          matmul_ok=ok, max_abs_error=error, checksum=c.double().sum().item())
except Exception as e:
 r['error'] = str(e)
 r['matmul_ok'] = False
print(json.dumps(r))
'''


def candidates():
    paths = [sys.executable, shutil.which('python'), shutil.which('python3')]
    for pattern in ('/root/*/bin/python*', '/opt/*/bin/python*', '/usr/local/*/bin/python*',
                    '/root/*/envs/*/bin/python*', '/opt/*/envs/*/bin/python*',
                    '/usr/local/*/envs/*/bin/python*', '/root/.conda/envs/*/bin/python*',
                    '/root/.virtualenvs/*/bin/python*'):
        paths.extend(glob.glob(pattern))
    seen = set()
    for p in paths:
        if not p or not re.fullmatch(r'python(?:\d+(?:\.\d+)?)?', Path(p).name):
            continue
        # venv interpreters can share a binary but have different site-packages.
        identity = (os.path.realpath(p), str(Path(p).parent))
        if identity not in seen and os.path.isfile(p) and os.access(p, os.X_OK):
            seen.add(identity)
            yield p


def run():
    result = {'passed': False, 'attempts': []}
    try:
        result['nvidia_smi'] = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
            text=True, timeout=15).strip()
    except (OSError, subprocess.SubprocessError) as e:
        result['nvidia_error'] = type(e).__name__
    for python in candidates():
        try:
            p = subprocess.run([python, '-c', CHECK], capture_output=True, text=True, timeout=45)
            lines = p.stdout.strip().splitlines()
            if p.returncode == 0 and lines:
                check = json.loads(lines[-1])
                result['attempts'].append(check)
                if check.get('matmul_ok') is True:
                    result.update(passed=True, selected=check)
                    break
            else:
                result['attempts'].append(dict(python=python, returncode=p.returncode,
                    error=p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'No JSON result'))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            result['attempts'].append(dict(python=python, error=type(e).__name__))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = run()
    data = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(data)
        temporary.replace(args.output)
    print(data)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
