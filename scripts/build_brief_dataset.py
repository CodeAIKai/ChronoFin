"""Build a small, explicitly author-curated public-source research dossier.

No complete report is redistributed. Cards are attributed paraphrases / facts,
not purported verbatim PDF extracts. No generated reference answers are used.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'brief'
SOURCES = [
    dict(id='meta24', entity='Meta', title='Meta Q4 and FY2024 earnings release', published_at='2025-01-29', period='FY2024',
         url='https://investor.atmeta.com/files/doc_financials/2024/q4/Meta-12-31-2024-Exhibit-99-1-FINAL.pdf', format='pdf', license='Facts and author paraphrases; original report copyright Meta'),
    dict(id='amazon24', entity='Amazon', title='Amazon Q4 and FY2024 earnings release', published_at='2025-02-06', period='FY2024',
         url='https://s2.q4cdn.com/299287126/files/doc_financials/2024/q4/AMZN-Q4-2024-Earnings-Release.pdf', format='pdf', license='Facts and author paraphrases; original report copyright Amazon'),
    dict(id='tsmc24', entity='TSMC', title='TSMC fourth-quarter results', published_at='2025-01-16', period='Q4 2024',
         url='https://pr.tsmc.com/english/news/3201', format='html', license='Facts and author paraphrases; original report copyright TSMC'),
    dict(id='iea25', entity='IEA / data centres', title='Energy and AI — executive summary', published_at='2025-04-10', period='2024–2035 scenarios',
         url='https://www.iea.org/reports/energy-and-ai/executive-summary', format='html', license='IEA (2025), Energy and AI, CC BY 4.0; author paraphrases, modified'),
    dict(id='fed25', entity='Federal Reserve / US financial system', title='April 2025 Financial Stability Report — overview', published_at='2025-05-07', period='data as of 2025-04-11',
         url='https://www.federalreserve.gov/publications/April-2025-financial-stability-report-Overview.htm', format='html', license='US Federal Reserve public report; author paraphrases',
         temporal_note='Conservative availability: current HTML last-update date; NOT claiming April 11 publication.'),
]

# (ID, document, locator, polarity, epistemic status, text, numeric value, unit)
ROWS = [
 ('M01','meta24','p1 annual revenue row','support','observed','Meta FY2024 revenue: USD 164501 million.',164501,'USD million'),
 ('M02','meta24','p1 annual net income row','support','observed','Meta FY2024 net income: USD 62360 million.',62360,'USD million'),
 ('M03','meta24','p9 segment operating results','caution','observed','Reality Labs FY2024 operating loss: USD 17729 million.',-17729,'USD million'),
 ('M04','meta24','p2 CFO outlook','caution','forecast','Meta anticipated FY2025 capital expenditures of USD 60–65 billion; guidance, not realized spending.',None,''),
 ('M05','meta24','p2 depreciation footnote','caution','forecast','Longer server lives were expected to reduce FY2025 depreciation by USD 2.9 billion; an accounting-estimate change.',2.9,'USD billion'),
 ('M06','meta24','p1 annual ad metrics','support','observed','FY2024 ad impressions grew 11%; average ad price rose 10%.',None,''),
 ('M07','meta24','p10 annual free cash flow','support','observed','Meta FY2024 free cash flow: USD 52103 million.',52103,'USD million'),
 ('M08','meta24','p4 non-GAAP definition','caution','definition','Meta free cash flow deducts property purchases and finance-lease principal; non-GAAP comparability is limited.',None,''),
 ('M09','meta24','p2 revenue outlook','caution','absence','Meta provided no FY2025 full-year revenue guidance in this release.',None,''),
 ('M10','meta24','p1 expense footnote','caution','observed','Q4 expenses benefited from a USD 1.55 billion reduction in accrued legal losses.',1.55,'USD billion'),
 ('A01','amazon24','p10 annual net sales','support','observed','Amazon FY2024 net sales: USD 637959 million.',637959,'USD million'),
 ('A02','amazon24','p10 annual operating income','support','observed','Amazon FY2024 operating income: USD 68593 million.',68593,'USD million'),
 ('A03','amazon24','p11 AWS annual sales','support','observed','AWS FY2024 net sales: USD 107556 million.',107556,'USD million'),
 ('A04','amazon24','p11 AWS annual operating income','support','observed','AWS FY2024 operating income: USD 39834 million.',39834,'USD million'),
 ('A05','amazon24','p10 annual free cash flow','caution','observed','Amazon FY2024 free cash flow: USD 38219 million.',38219,'USD million'),
 ('A09','amazon24','p10 annual free cash flow','context','observed','Amazon FY2023 free cash flow: USD 36813 million.',36813,'USD million'),
 ('A06','amazon24','p10 annual operating cash flow','support','observed','FY2024 operating cash flow reached about USD 115.9 billion, a 36% increase.',115.9,'USD billion'),
 ('A07','amazon24','p10 FCF definition footnotes','caution','definition','Amazon headline free cash flow deducts net property purchases; separate variants also deduct lease principal.',None,''),
 ('A08','amazon24','p11 AWS quarterly margins','caution','observed','AWS operating margin: Q3 2024 38.1%; Q4 2024 36.9%.',None,''),
 ('T01','tsmc24','opening results paragraph','support','observed','TSMC Q4 2024 revenue: TWD 868.46 billion.',868.46,'TWD billion'),
 ('T02','tsmc24','year-over-year paragraph','support','observed','Q4 2024 revenue grew 38.8% measured in TWD.',38.8,'%'),
 ('T03','tsmc24','USD results paragraph','context','observed','Q4 2024 revenue grew 37.0% measured in USD.',37.0,'%'),
 ('T04','tsmc24','margin paragraph','support','observed','TSMC Q4 2024 gross margin: 59.0%.',59.0,'%'),
 ('T07','tsmc24','margin paragraph','context','observed','TSMC Q4 2024 net profit margin: 43.1%.',43.1,'%'),
 ('T05','tsmc24','technology mix paragraph','support','observed','Nodes of 7nm or smaller contributed 74% of Q4 wafer revenue.',74,'%'),
 ('T06','tsmc24','CFO outlook paragraph','caution','forecast','Management expected smartphone seasonality in Q1 2025, partly offset by AI demand growth.',None,''),
 ('I01','iea25','current consumption section','context','estimate','IEA estimated 2024 data-centre electricity use at 415 TWh, about 1.5% globally.',415,'TWh'),
 ('I02','iea25','2030 outlook section','support','forecast','IEA projected data-centre electricity demand of around 945 TWh in 2030.',945,'TWh'),
 ('I03','iea25','grid integration section','caution','forecast','Without action, grid constraints could delay around 20% of planned data-centre projects.',20,'%'),
 ('I04','iea25','uncertainty section','caution','forecast','IEA scenario range for 2035 data-centre demand: 700–1700 TWh; adoption, efficiency and bottlenecks matter.',None,''),
 ('I05','iea25','global demand growth section','caution','forecast','Data centres represent roughly one-tenth of projected global electricity-demand growth through 2030.',None,''),
 ('I06','iea25','energy efficiency section','support','forecast','AI applications could improve grid management and industrial efficiency; deployment barriers remain.',None,''),
 ('F01','fed25','overview opening','context','observed','The assessment uses market conditions and data through April 11, 2025.',None,''),
 ('F02','fed25','asset valuations','caution','observed','Equity valuations remained high versus expected earnings; liquidity deteriorated, with generally orderly functioning.',None,''),
 ('F03','fed25','financial leverage','caution','observed','Hedge-fund leverage indicators were near decade highs and concentrated in larger funds.',None,''),
 ('F04','fed25','financial leverage','support','observed','Banks remained broadly resilient, with most reporting capital well above regulatory requirements.',None,''),
 ('F05','fed25','household and business debt','support','observed','Business and household debt vulnerabilities were moderate; debt relative to GDP had declined.',None,''),
 ('F06','fed25','funding risks','support','observed','Funding vulnerabilities had declined to moderate levels; runnable liabilities remained a persistent risk.',None,''),
 ('F07','fed25','household credit','caution','observed','Credit-card and auto delinquencies exceeded pre-pandemic levels, especially among non-prime borrowers.',None,''),
]

def case(i, split, group, mode, q, required, counter, limits, answerability='answerable', cutoff='2025-06-01', difficulty='hard'):
    return dict(id=i, split=split, source_group=group, task=mode, question=q, as_of=cutoff,
                difficulty=difficulty, required=required, counter=counter, limitations=limits,
                expected_answerability=answerability)

CASES = [
 case('D01','dev','meta24','财报阅读','为研究晨会概括 Meta FY2024 盈利质量：业务驱动、利润与现金流、反面证据和后续核查。',['M01','M02','M06','M07'],['M03','M10'],['一次性因素不能代表持续经营改善']),
 case('D02','dev','amazon24','财报阅读','用 Amazon FY2024 财报解释 AWS 对集团利润的重要性，并评估利润改善是否同步转化为现金。',['A01','A02','A03','A04'],['A05','A08'],['不能把 AWS 的收入占比称为行业市场份额']),
 case('D03','dev','tsmc24','公开数据问答','TSMC Q4 2024 收入增长有多强？解释不同币种增速，并给出谨慎的短期展望。',['T01','T02','T03','T05'],['T06'],['单季结果不可冒充全年']),
 case('D04','dev','iea25','行业研报摘要','向电力设备研究员摘要 IEA 的 AI 用电展望：机会、规模、制约因素和可跟踪指标。',['I01','I02','I06'],['I03','I04','I05'],['预测不能表述为已实现事实']),
 case('D05','dev','fed25','行业研报摘要','将美联储稳定性报告整理成信用研究晨会简报，分别说明风险与缓冲。',['F01','F02','F03'],['F04','F05','F06','F07'],['风险描述不是危机发生概率']),
 case('E01','evaluation','meta24','财报阅读','据 Meta 披露写 FY2025 投入与盈利展望：能否确认全年收入及资本回报率？',['M04','M05','M09'],['M03'],['全年收入实际值和 AI 投资回报率均未由材料提供'],'partial'),
 case('E02','evaluation','meta24','公开数据问答','截至 2025-01-28，根据提供的披露总结 Meta FY2024 全年经营表现。',[],[],['给定材料在截止日后发布，不能利用后来的财报'],'unanswerable','2025-01-28'),
 case('E03','evaluation','meta24','财报阅读','Meta 利润改善是否全由运营效率带来？写一段有反证的研究结论。',['M02','M06'],['M10','M05','M03'],['区分 FY2024 一次性法律费用影响与 FY2025 折旧估计']),
 case('E04','evaluation','cross','财报阅读','比较 Meta 与 Amazon FY2024 自由现金流，能否直接据数值大小断言现金创造效率更高？',['M07','A05'],['M08','A07'],['口径和业务规模不同；不可直接做效率排名']),
 case('E05','evaluation','amazon24','公开数据问答','给出 AWS FY2024 营业利润率及对 Amazon 集团营业利润的占比，解释它们说明什么、不说明什么。',['A02','A03','A04'],['A08'],['缺少行业总额，不能推断市场份额']),
 case('E06','evaluation','amazon24','财报阅读','Amazon 经营现金流增长能否证明其 AI 投资已经获得高回报？写有依据的简报。',['A06','A04'],['A05','A07'],['未提供 AI 单独成本与收益，不能计算 AI 投资回报率'],'partial'),
 case('E07','evaluation','tsmc24','公开数据问答','有人说 TSMC 2024 全年收入为 TWD 868.46 billion、净利率为 43.1%。核对并解释正确期间。',['T01','T07'],['T06'],['这两个数据属于 Q4，不能改称全年']),
 case('E08','evaluation','tsmc24','公开数据问答','TSMC Q4 的 TWD 与 USD 收入同比增速相差多少？解释百分比和百分点的区别。',['T02','T03'],[],['差值是 1.8 个百分点；不同币种口径不是矛盾'],difficulty='standard'),
 case('E09','evaluation','tsmc24','财报阅读','依据 TSMC 的先进制程占比和管理层展望，分析 AI 景气能否完全消除手机季节性。',['T05','T06'],['T06'],['无法量化两类需求净影响，不应保证消除季节性']),
 case('E10','evaluation','iea25','行业研报摘要','评审观点“数据中心 2030 年已经消耗 945 TWh，因此电力需求一定实现”。给出证据化纠正。',['I01','I02'],['I03','I04'],['2030 数据是预测，存在情景与瓶颈风险']),
 case('E11','evaluation','cross','行业研报摘要','综合 Meta AI 资本支出展望与 IEA 用电研究，写一段基础设施机会和约束简报。',['M04','I02'],['I03','I04','M05'],['公司指引与行业情景不是同一口径；不能推导确定投资收益']),
 case('E12','evaluation','iea25','公开数据问答','IEA 数据中心用电预测为什么不应只给单点值？比较 2030 展望与 2035 情景范围。',['I02','I04'],['I03'],['不得把不同预测年度混为同一区间']),
 case('E13','evaluation','fed25','行业研报摘要','有人把高对冲基金杠杆解读为银行系统已经失稳。依据报告写一段平衡核查。',['F03','F04'],['F05','F06'],['对冲基金与银行是不同主体，风险不是已发生危机']),
 case('E14','evaluation','fed25','公开数据问答','截至 2025-04-11，根据当前这份美联储网页说明当时已经公开的稳定性结论。',[],[],['数据截止日不是网页公开日；此清单采用 2025-05-07 保守可知日期'],'unanswerable','2025-04-11'),
 case('E15','evaluation','fed25','行业研报摘要','概括报告最值得信用研究员跟踪的两类风险和两类缓冲，并说明它不能支持哪些确定性结论。',['F02','F03','F07'],['F04','F05','F06'],['没有提供危机概率，也不构成个性化交易建议']),
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index={s['id']:s for s in SOURCES}
    cards=[]
    for i,d,loc,role,status,text,value,unit in ROWS:
        cards.append(dict(id=i,source_id=d,locator=loc,role=role,status=status,text=text,value=value,unit=unit,
                          entity=index[d]['entity'],published_at=index[d]['published_at']))
    for name,obj in [('sources.json',SOURCES),('cards.json',cards),('cases.json',CASES)]:
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sources':len(SOURCES),'cards':len(cards),'cases':len(CASES),'dev':5,'evaluation':15}))

if __name__=='__main__': main()
