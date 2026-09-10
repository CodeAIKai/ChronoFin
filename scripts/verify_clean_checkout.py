"""Verify a fresh source copy without keys or raw-report caches on this host.

This is checkout isolation with the current interpreter, not a third-party or
container reproduction. A child-process audit hook blocks non-loopback network.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','__pycache__','.pytest_cache','data/cache','.env'}

def fingerprint(root):
    files={}
    selected=[root/'src',root/'scripts',root/'tests',root/'web',root/'data']
    for base in selected:
        for p in sorted(base.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or 'cache' in p.parts or any(part.endswith('.egg-info') for part in p.parts):continue
            files[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ['research_app.py','pyproject.toml','README.md','.env.example']:
        files[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
    tree=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'sha256':tree,'files':files}

def main():
    original_fingerprint=fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='chronofin-clean-') as temp:
        directory=Path(temp);copy=directory/'code';guard=directory/'network_guard';guard.mkdir()
        def ignore(path,names):
            relative=Path(path).relative_to(ROOT)
            return [n for n in names if n in {'.git','.venv','__pycache__','.pytest_cache','.env'}
                    or n.endswith('.egg-info') or (n.startswith('.env.') and n!='.env.example')
                    or (relative==Path('data') and n=='cache')]
        shutil.copytree(ROOT,copy,ignore=ignore)
        if fingerprint(copy)!=original_fingerprint:raise RuntimeError('Copied source differs from original fingerprint')
        (guard/'sitecustomize.py').write_text('''import sys
def restrict(event,args):
    if event=='socket.connect':
        address=args[1]
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            raise RuntimeError('clean-checkout blocks non-loopback network')
sys.addaudithook(restrict)
''')
        env={k:v for k,v in os.environ.items() if k not in {'HY3_API_KEY','OPENAI_API_KEY','PYTHONPATH'}}
        env.update(PYTHONPATH=str(guard)+os.pathsep+str(copy/'src'),PIP_NO_INDEX='1',NO_PROXY='*',PYTHONDONTWRITEBYTECODE='1')
        commands=[['-m','unittest','discover','-s','tests','-t','.','-v'],
                  ['scripts/run_brief_experiments.py','--phase','replay','--run','v3'],
                  ['scripts/resume_brief.py'],['scripts/verify_extended.py'],['scripts/verify_artifacts.py']]
        records=[]
        for i,args in enumerate(commands):
            started=time.monotonic()
            run=subprocess.run([sys.executable,*args],cwd=copy,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
            log=ROOT/'audit'/f'clean_checkout_step{i+1}.log';log.write_text(run.stdout)
            item={'argv':['python',*args],'exit_code':run.returncode,'elapsed_seconds':round(time.monotonic()-started,3),
                  'log':str(log.relative_to(ROOT)),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
            records.append(item);print(json.dumps(item),flush=True)
        out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pass':all(r['exit_code']==0 for r in records) and fingerprint(ROOT)==original_fingerprint,
             'source_fingerprint':original_fingerprint,'commands':records,'api_key_present':False,
             'non_loopback_network':'blocked by audit hook in child Python processes','raw_report_cache_present':(copy/'data/cache').exists(),
             'interpreter':sys.executable,'scope':'Fresh temporary checkout, same host and installed interpreter; not independent expert, container, or third-party reproduction.'}
        (ROOT/'audit/clean_checkout_verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
        raise SystemExit(not out['pass'])

if __name__=='__main__':main()
