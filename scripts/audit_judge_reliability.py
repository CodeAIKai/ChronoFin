"""Reproducible, zero-model-call audit of saved judge disagreements."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin.brief import read_data
from chronofin.reliability import reliability_envelope

def main():
    folder=ROOT/'results/brief/v3';_,cards,_=read_data(ROOT);out={}
    for i in ['D01','D04','D05']:
        base=json.loads((folder/f'{i}_counterbrief.json').read_text())
        repeated=[json.loads(p.read_text()) for p in sorted((folder/'metaeval').glob(f'{i}_repeat_*.json'))]
        out[i]=reliability_envelope(base,repeated,cards)
    target=folder/'judge_reliability.json';target.write_text(json.dumps({'model_calls':0,'cases':out},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({i:{k:v for k,v in d.items() if k in ['status','n_judgments','observed_score_interval','range']} for i,d in out.items()},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
