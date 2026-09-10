"""Build an editable, font-embedded architecture figure from explicit coordinates."""
from pathlib import Path
from xml.sax.saxutils import escape
import base64,io,json
from fontTools import subset
from fontTools.ttLib import TTFont
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
W,H=1760,1376
INK='#17383C';MUTED='#5C7074';TEAL='#197D70';LINE='#CAD7D8';BLUE='#367782'
parts=[];texts=[];nodes=[];edges=[]
def rect(x,y,w,h,fill,stroke='none',rx=0,sw=1):
 parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def text(x,y,s,size=24,color=INK,weight=400,box=None):
 tid=f't{len(texts)}';texts.append({'id':tid,'text':s,'container':box,'x':x,'baseline':y})
 parts.append(f'<text id="{tid}" x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(s)}</text>')
def card(cid,x,y,w,h,title,number,fill='#FFFFFF'):
 node={'id':cid,'x':x,'y':y,'w':w,'h':h};nodes.append(node);rect(x,y,w,h,fill,LINE,10,1.4)
 text(x+26,y+36,number,18,MUTED,600,cid);text(x+26,y+83,title,29,INK,600,cid)
 parts.append(f'<path d="M{x+26} {y+105}H{x+w-26}" fill="none" stroke="{LINE}"/>')
 return node

def arrow(eid,points,color=BLUE):
 edges.append({'id':eid,'points':points,'color':color});d='M'+' L'.join(f'{x} {y}' for x,y in points)
 marker='teal' if color==BLUE else 'gray'
 parts.append(f'<path id="{eid}" d="{d}" fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#{marker})"/>')
rect(0,0,W,H,'#FFFFFF')
text(64,43,'CHRONOFIN  /  SYSTEM ARCHITECTURE',17,MUTED,600)
text(64,111,'时证：金融研究与证据核查',44,INK,600)
text(64,164,'从可知资料生成研究结论，再验证结论与评判依据。',25,MUTED)
rect(1356,67,340,57,'#EAF3F0','none',7)
text(1382,103,'Hy3  ·  无训练或微调',23,TEAL,600)
parts.append(f'<path d="M64 186H1696" stroke="{LINE}"/>')
text(64,220,'01  应用流程',27,INK,600)
text(1075,220,'模型调用统一经腾讯 TokenHub / Hy3',23,MUTED)
card('input',64,252,360,324,'研究任务与资料','INPUT')
for y,s in [(396,'问题、公司与信息截止日'),(439,'文字 PDF / 公开资料卡'),(482,'来源日期、页码与单位')]:text(90,y,s,24,box='input')
text(90,541,'财报阅读 · 研报摘要 · 公开问答',20,MUTED,box='input')
card('evidence',488,252,360,324,'时点与原文证据','EVIDENCE')
for y,s in [(396,'披露日期过滤与片段检索'),(439,'PDF：Hy3 选择原文行'),(482,'程序回绑原句与登记数值')]:text(514,y,s,24,box='evidence')
text(514,541,'未来正文在模型调用前隔离',20,TEAL,box='evidence')
card('generation',912,252,360,324,'生成与反证修订','HY3 + LOCAL CHECKS','#EAF3F0')
for y,s in [(396,'Hy3 生成带引用的初稿'),(439,'本地计算、单位与绑定核验'),(482,'Hy3 检查反证、口径与边界')]:text(938,y,s,23,box='generation')
text(938,541,'原稿、修订与调用记录均保留',20,TEAL,box='generation')
card('workbench',1336,252,360,324,'可复核研究简报','WORKBENCH')
for y,s in [(396,'研究结论与原文引用'),(439,'证据账本与待核查事项'),(482,'分维诊断与 JSON 导出')]:text(1362,y,s,24,box='workbench')
text(1362,541,'实时分析 / 已保存的真实结果回放',19,MUTED,box='workbench')
for i,(a,b) in enumerate([(424,488),(848,912),(1272,1336)]):arrow('application_'+str(i),[(a,414),(b,414)])
arrow('candidate_to_evaluation',[(1092,576),(1092,628),(880,628),(880,772)])
text(936,615,'候选答卷',21,BLUE)
arrow('diagnostics_to_workbench',[(1074,772),(1074,691),(1516,691),(1516,576)],'#778E93')
text(1200,678,'分维诊断与核查依据',21,MUTED)
text(64,722,'02  评估与方法验证',27,INK,600)
card('reference',64,772,496,330,'评测样本与参考要点','EVALUATION INPUTS','#F6F8F8')
for y,s in [(917,'原文证据与参考清单'),(960,'真实案例、难例与反例'),(1003,'退化、等价与注入变形')]:text(90,y,s,24,box='reference')
text(90,1069,'参考清单不进入生成或修订提示',21,TEAL,box='reference')
card('evaluation',632,772,496,330,'十维评估','RULES + HY3 JUDGE','#F6F8F8')
text(658,917,'规则校验 + Hy3 语义评判',24,box='evaluation')
text(658,955,'原文与候选原句绑定 · 逐项判据',23,box='evaluation')
text(658,993,'诊断分聚合与错误门禁',23,box='evaluation')
parts.append(f'<path d="M658 1015H1102" stroke="{LINE}"/>')
text(658,1043,'无独立参考清单：三维标为未测',21,TEAL,box='evaluation')
text(658,1080,'不报告汇总分',21,TEAL,box='evaluation')
card('validation',1200,772,496,330,'评估方法验证','VALIDATION','#F6F8F8')
for y,s in [(917,'判别力 · 一致性 · 对抗性'),(960,'同调用次数的应用对照'),(1003,'完整结果、失败归因与可复现记录')]:text(1226,y,s,23,box='validation')
text(1226,1069,'公开人工标签用于三分类一致性验证',20,MUTED,box='validation')
arrow('reference_to_evaluation',[(560,938),(632,938)])
arrow('evaluation_to_validation',[(1128,938),(1200,938)])
rect(64,1139,1632,158,'#F2F6F4','none',10)
text(90,1178,'10 个可操作维度',23,TEAL,600)
labels=[['时点与披露','来源与引用覆盖','原子事实与摘要','数值与可执行计算','重要信息覆盖'],['反证与平衡','实体、期间与口径','预测、推断与未知边界','可理解性与核查价值','注入与越权建议']]
for row,values in enumerate(labels):
 for col,s in enumerate(values):text(90+col*321,1224+row*43,s,22,INK)
text(64,1341,'2026 腾讯犀牛鸟开源人才培养计划 · 个人活动作品',20,MUTED)
text(1110,1341,'程序校验存在性，语义判断仍需复核。',20,MUTED)
# Embed only the glyphs used by this figure, so text layout does not depend on system fonts.
font=TTFont(str(REPO/'assets/fonts/NotoSansCJKsc-Regular.otf'))
options=subset.Options();options.layout_features=[];subsetter=subset.Subsetter(options=options);subsetter.populate(text=''.join(t['text'] for t in texts));subsetter.subset(font)
for record in font['name'].names:
 if record.nameID in [1,4,6]:
  name='ChronoFinDiagram' if record.nameID==6 else 'ChronoFin Diagram'
  record.string=name.encode(record.getEncoding(),errors='replace')
buffer=io.BytesIO();font.save(buffer);encoded=base64.b64encode(buffer.getvalue()).decode()
header=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="figure-title figure-desc">
<title id="figure-title">时证金融研究应用与评估架构</title>
<desc id="figure-desc">应用由研究输入、时点和原文证据、Hy3生成与反证修订、研究工作台组成；候选答卷进入十维评估，评估依据返回工作台，参考要点只供评判使用，评估器另做判别力、一致性与对抗性验证。</desc>
<defs><style>@font-face{{font-family:ChronoFinDiagram;src:url(data:font/otf;base64,{encoded}) format('opentype');font-weight:100 900}}text{{font-family:ChronoFinDiagram,sans-serif}}</style>
<marker id="teal" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L8 4.5L0 9" fill="none" stroke="{BLUE}" stroke-width="1.9"/></marker>
<marker id="gray" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L8 4.5L0 9" fill="none" stroke="#778E93" stroke-width="1.9"/></marker></defs>
'''
(ROOT/'chronofin_architecture.svg').write_text(header+'\n'.join(parts)+'\n</svg>\n')
(ROOT/'layout.json').write_text(json.dumps({'width':W,'height':H,'nodes':nodes,'edges':edges,'texts':texts},ensure_ascii=False,indent=2)+'\n')
print('svg_ready',len(texts),'text_elements',len(nodes),'cards',len(edges),'connectors',len(buffer.getvalue()),'font_bytes')
