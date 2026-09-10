"""Resume frozen v1 payloads with shared-account throttling, keeping failures."""
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
import run_external_human_audit as frozen
from chronofin.runtime import RateLimitedClient

def main():
    folder=ROOT/'results/external_human/v1'
    first=folder/'first_attempt_summary.json'
    if not first.exists():first.write_bytes((folder/'summary.json').read_bytes())
    archived=[]
    for p in folder.glob('financebench_id_*.json'):
        if json.loads(p.read_text()).get('status')!='ok':
            target=folder/'attempt_history'/(p.stem+'.'+str(time.time_ns())+'.json')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());archived.append(str(target.relative_to(ROOT)))
    audit={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archived':archived,
           'transport_override':'RateLimitedClient; unchanged model, prompts, selected responses and reference version.',
           'runtime_sha256':hashlib.sha256((ROOT/'src/chronofin/runtime.py').read_bytes()).hexdigest()}
    (folder/'transport_resume.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    frozen.ChatCompletionsClient=RateLimitedClient
    sys.argv=[str(ROOT/'scripts/run_external_human_audit.py'),'--execute','--workers','3']
    frozen.main()

if __name__=='__main__':main()
