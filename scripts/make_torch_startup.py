#!/usr/bin/env python3
"""Build a short Matpool startup script that finds PyTorch and checks CUDA."""
import argparse
import re


def build(filename):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}\.json', filename):
        raise ValueError('Use a simple JSON basename, without a directory or shell characters')
    code = ('import torch,json,sys; a=torch.ones((256,256),device="cuda"); b=a@a; '
            'torch.cuda.synchronize(); assert bool(torch.all(b==256)); '
            'print(json.dumps(dict(passed=True,python=sys.executable,torch_version=torch.__version__,'
            'cuda_runtime=torch.version.cuda,device=torch.cuda.get_device_name(0),'
            'result_device=str(b.device),shape=list(b.shape),checksum=b.sum().item())))')
    script = ('#!/bin/bash\nmkdir -p /tmp/codex-smoke\n'
              'for p in /root/*/bin/python /opt/*/bin/python /usr/local/*/bin/python '
              '/root/*/envs/*/bin/python /opt/*/envs/*/bin/python /usr/bin/python3; do\n'
              '[ -x "$p" ] || continue\n'
              '"$p" -c \'' + code + '\' >/tmp/codex-smoke/result.tmp '
              '2>>/tmp/codex-smoke/errors.txt && { mv /tmp/codex-smoke/result.tmp '
              '/tmp/codex-smoke/' + filename + '; break; }\ndone\n'
              'timeout 240s python3 -m http.server 8895 --directory /tmp/codex-smoke\n')
    if len(script.encode()) > 1024:
        raise ValueError('Generated command exceeds the verified startup limit')
    return script


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--result-file', default='torch-result.json')
    args = p.parse_args()
    print(build(args.result_file), end='')
