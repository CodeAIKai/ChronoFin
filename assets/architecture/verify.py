"""Render the figure and verify every label and connector against its actual geometry."""
from pathlib import Path
import json,hashlib,itertools
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;layout=json.loads((ROOT/'layout.json').read_text())
node_by_id={x['id']:x for x in layout['nodes']}
def overlaps(a,b,pad=0):
 return min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x'])>pad and min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y'])>pad

def segment_enters(a,b,r,pad=0):
 x,y=a;xx,yy=b;l=r['x']+pad;right=r['x']+r['w']-pad;top=r['y']+pad;bottom=r['y']+r['h']-pad
 if x==xx:return l<x<right and min(max(y,yy),bottom)>max(min(y,yy),top)
 assert y==yy
 return top<y<bottom and min(max(x,xx),right)>max(min(x,xx),l)

def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':layout['width'],'height':layout['height']},device_scale_factor=2)
  page.goto((ROOT/'chronofin_architecture.svg').as_uri());page.evaluate('document.fonts.ready');page.wait_for_timeout(300)
  boxes=page.evaluate('''()=>Object.fromEntries([...document.querySelectorAll('text')].map(t=>{const r=t.getBBox();return [t.id,{x:r.x,y:r.y,w:r.width,h:r.height}]}))''')
  font=page.evaluate('document.fonts.check("24px ChronoFinDiagram")');assert font
  errors=[]
  for t in layout['texts']:
   b=boxes[t['id']];outer=node_by_id.get(t['container'],{'x':0,'y':0,'w':layout['width'],'h':layout['height']});padding=15 if t['container'] else 4
   if b['x']<outer['x']+padding or b['x']+b['w']>outer['x']+outer['w']-padding or b['y']<outer['y']+padding or b['y']+b['h']>outer['y']+outer['h']-padding:errors.append({'type':'text_overflow','text':t['text'],'bbox':b,'container':outer})
  for a,b in itertools.combinations(layout['texts'],2):
   if overlaps(boxes[a['id']],boxes[b['id']],.2):errors.append({'type':'text_overlap','texts':[a['text'],b['text']]})
  segments=[]
  for e in layout['edges']:
   for a,b in zip(e['points'],e['points'][1:]):
    segments.append((e['id'],a,b))
    for n in layout['nodes']:
     if segment_enters(a,b,n,.1):errors.append({'type':'connector_crosses_card','edge':e['id'],'card':n['id']})
    for t in layout['texts']:
     r=dict(boxes[t['id']]);r['x']-=3;r['y']-=3;r['w']+=6;r['h']+=6
     if segment_enters(a,b,r):errors.append({'type':'connector_crosses_text','edge':e['id'],'text':t['text']})
  for (eid,a,b),(fid,c,d) in itertools.combinations(segments,2):
   if eid==fid:continue
   if a[0]==b[0] and c[1]==d[1] and min(c[0],d[0])<a[0]<max(c[0],d[0]) and min(a[1],b[1])<c[1]<max(a[1],b[1]):errors.append({'type':'connector_crossing','edges':[eid,fid]})
   if a[1]==b[1] and c[0]==d[0] and min(a[0],b[0])<c[0]<max(a[0],b[0]) and min(c[1],d[1])<a[1]<max(c[1],d[1]):errors.append({'type':'connector_crossing','edges':[eid,fid]})
  report={'pass':not errors,'labels_checked':len(layout['texts']),'cards_checked':len(layout['nodes']),'connectors_checked':len(layout['edges']),'font_loaded':font,'errors':errors,'svg_sha256':hashlib.sha256((ROOT/'chronofin_architecture.svg').read_bytes()).hexdigest(),'text_bounds':boxes,'scope':'Browser-rendered SVG text bounding boxes, box containment, label overlap, and orthogonal connector/card/text intersection checks.'}
  (ROOT/'layout_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({k:v for k,v in report.items() if k!='text_bounds'},ensure_ascii=False,indent=2),flush=True)
  assert not errors,'Fix layout errors before publishing'
  page.screenshot(path=str(ROOT/'chronofin_architecture.png'));page.pdf(path=str(ROOT/'chronofin_architecture.pdf'),width=f"{layout['width']}px",height=f"{layout['height']}px",print_background=True,margin={'top':'0','bottom':'0','left':'0','right':'0'})
  browser.close()
if __name__=='__main__':main()
