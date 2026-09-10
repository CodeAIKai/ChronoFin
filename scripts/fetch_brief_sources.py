"""Re-fetch official originals; compare pinned bytes, never silently replace."""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--offline',action='store_true');args=p.parse_args()
    sources=json.loads((ROOT/'data/brief/sources.json').read_text())
    pins={s['source_id']:s for s in json.loads((ROOT/'data/brief/source_snapshots.json').read_text())}
    cache=ROOT/'data/cache/brief';cache.mkdir(parents=True,exist_ok=True)
    def work(s):
        path=cache/(s['id']+'.'+s['format'])
        try:
            if not path.exists():
                if args.offline:raise ValueError('original absent; run online downloader')
                req=urllib.request.Request(s['url'],headers={'User-Agent':'Mozilla/5.0 (ChronoFin research)'})
                with urllib.request.urlopen(req,timeout=60) as r:data=r.read()
            else:data=path.read_bytes()
            sha=hashlib.sha256(data).hexdigest();same=sha==pins[s['id']]['sha256']
            if same and not path.exists():path.write_bytes(data)
            return {'source_id':s['id'],'status':'verified' if same else 'changed_upstream_bytes',
                    'sha256':sha,'expected_sha256':pins[s['id']]['sha256'],
                    'note':'HTML may change without material financial changes; review new version explicitly.' if not same else ''}
        except Exception as e:return {'source_id':s['id'],'status':'error','error':str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:r=list(pool.map(work,sources))
    out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':r}
    target=ROOT/'results/source_verification.json';target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    raise SystemExit(any(x['status']!='verified' for x in r))

if __name__=='__main__':main()
