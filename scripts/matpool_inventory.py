#!/usr/bin/env python3
"""Read Matpool's public market inventory without account credentials."""
import argparse
from datetime import datetime, timezone
import json
import sys
import urllib.parse
import urllib.request
from matpool_api import NoRedirect

URL = 'https://matgo.cn/api/machine_pools'


def summarize(pool):
    machine = pool.get('machine', {})
    hardware = machine.get('hardware', {})
    gpu = hardware.get('gpu', {})
    resources = hardware.get('machine', {})
    price = hardware.get('discountPriceMillicent', hardware.get('priceMillicent'))
    return {'gpu': pool.get('gpu_model'), 'domain_id': pool.get('domain'),
            'driver': pool.get('driver_version'), 'available_units': pool.get('max_available_units'),
            'memory_mb': gpu.get('gpuRamMB'), 'ram_mb': resources.get('ramMB'),
            'disk_gb': resources.get('diskGB'),
            'hourly_cny_per_unit': price / 100000 if isinstance(price, (int, float)) else None,
            'resource_pool_id': pool.get('resource_pool_id'),
            'representative_agent_id': machine.get('agentId')}


def fetch(gpu_filter='', domain=None):
    opener = urllib.request.build_opener(NoRedirect())
    rows, page = [], 1
    while True:
        query = urllib.parse.urlencode({'machine_category': 0, 'page': page, 'per_page': 100})
        req = urllib.request.Request(URL + '?' + query, headers={'Accept': 'application/json'})
        with opener.open(req, timeout=25) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get('code', 0) != 0 or not isinstance(data.get('pools'), list):
            raise ValueError('Unexpected inventory response; do not infer zero availability')
        rows.extend(summarize(p) for p in data['pools']
                    if gpu_filter.lower() in p.get('gpu_model', '').lower()
                    and (domain is None or p.get('domain') == domain))
        pages = data.get('pagination', {}).get('num_pages', 1)
        if not isinstance(pages, int) or pages < 1 or pages > 100:
            raise ValueError('Unexpected pagination; inventory may be incomplete')
        if page >= pages:
            break
        page += 1
    rows.sort(key=lambda r: (r['hourly_cny_per_unit'] is None, r['hourly_cny_per_unit'] or 0,
                             r['gpu'] or '', r['driver'] or ''))
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'source': URL,
            'scope': 'Market resource pools, not a PaaS scheduling guarantee', 'pools': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu', default='', help='Case-insensitive model name substring')
    p.add_argument('--domain', type=int, help='Verified region ID; region 1 is ID 0')
    args = p.parse_args()
    try:
        print(json.dumps(fetch(args.gpu, args.domain), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f'Inventory query failed ({type(exc).__name__}); no rental was attempted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
