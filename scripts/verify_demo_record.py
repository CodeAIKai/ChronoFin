"""Verify saved demonstration provenance and recompute its fresh score offline."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief

def main():
    folder=ROOT/'results/demo';result=json.loads((folder/'TC01_demo.json').read_text());protocol=json.loads((folder/'revision_protocol.json').read_text())
    parent=ROOT/protocol['origin'];old=json.loads(parent.read_text());r=result['record'];revision=r['demo_revision'];sem=result['semantic']
    assert result['status']=='ok'
    assert hashlib.sha256(parent.read_bytes()).hexdigest()==protocol['origin_sha256']==revision['parent_record_sha256']
    assert brief.digest(old['record']['answer'])==revision['parent_answer_sha256']
    assert r['answer']==revision['response']
    assert brief.digest(r['answer'])==r['answer_sha256']==sem['answer_sha256']
    assert brief.digest(protocol['prompt'])==revision['input_sha256']
    assert brief.digest(protocol['system'])==revision['system_sha256']
    assert hashlib.sha256((folder/'revision_protocol.json').read_bytes()).hexdigest()==result['protocol_sha256']
    assert revision['trace']['model']==sem['trace']['model']=='hy3'
    material=result['replay_material'];score=brief.evaluate(r,material['reference_case'],material['audit_cards'],sem)
    assert brief.digest(score)==brief.digest(result['scorecard'])
    assert r['source_document']==old['record']['source_document']
    assert r['evidence']==old['record']['evidence']
    print(json.dumps({'pass':True,'case':'TC01_demo','answer_sha256':r['answer_sha256'],'fresh_judgment_bound':True,'score_recomputed':score['score'],'parent_record_unchanged':True,'scope':'Demonstration revision; excluded from the original benchmark aggregates.'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
