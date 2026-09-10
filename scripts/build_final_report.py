"""Build current, evidence-based final analysis; no online calls."""
import collections
import datetime
import json
from pathlib import Path
import re
import statistics

ROOT=Path(__file__).resolve().parents[1]
def load(p,default=None):return json.loads(p.read_text())if p.exists()else default
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    app=load(ROOT/'results/brief/v3/summary.json',{});meta=load(ROOT/'results/brief/v3/metaeval/summary.json',{})
    ext=load(ROOT/'results/extended_analysis.json',{});human=load(ROOT/'results/external_human/v3/summary.json',{})
    ground=load(ROOT/'results/grounded/v1/summary.json',{});native=load(ROOT/'results/native_pdf/v5/summary.json',{})
    nv=load(ROOT/'results/native_validation/v2/summary.json',{});stress=load(ROOT/'results/semantic_stress/v1/summary.json',{})
    rows=[load(p)for p in (ROOT/'results/brief/v3').glob('[DE][0-9][0-9]_*.json')];pairs=[]
    for cid in sorted({r['case_id']for r in rows if r['split']=='evaluation'}):
        rr={r['strategy']:r for r in rows if r['case_id']==cid and r['status']=='ok'}
        if len(rr)==3:pairs.append({'case_id':cid,**{s:r['scorecard']['score']for s,r in rr.items()}})
    completed=sum(r['status']=='ok'for r in rows);usage=ext.get('usage_lower_bound',{})
    planned={'brief_application':[completed,60],'brief_meta':[meta.get('n',0)-meta.get('failures',0),30],
             'equal_call_application':[ground.get('application_complete',0),80],'order_judgments':[ground.get('order_complete',0),48],
             'external_human_v3':[human.get('complete',0),600],'semantic_stress':[stress.get('complete',0),60],
             'native_pdf_v5':[native.get('complete',0),12],'native_final_validation':[nv.get('complete',0),30]}
    pending=sum(n-c for c,n in planned.values());versions={}
    for v in ['v1','v2','v3']:
        rr=[load(p)for p in (ROOT/'results/brief'/v).glob('[DE][0-9][0-9]_*.json')if '.failed_'not in p.name]
        versions[v]={'records':len(rr),'ok':sum(r['status']=='ok'for r in rr),'errors':sum(r['status']!='ok'for r in rr)}
    status={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version_status':versions,
            'final_app_completed':completed,'final_app_planned':60,'final_app_incomplete':60-completed,
            'meta_planned':30,'meta_completed':planned['brief_meta'][0],'pending_online':pending,'all_online_completed':pending==0,
            'experiment_completion':planned,'complete_evaluation_pairs':pairs,
            'complete_pair_means':{s:statistics.mean(p[s]for p in pairs)for s in ['lexical','full_context','counterbrief']}if pairs else {},
            'reported_calls_lower_bound':usage.get('unique_successful_request_traces'),
            'reported_tokens_lower_bound':usage.get('total_tokens'),'native_final_version':'v5',
            'new_expert_annotation_executed':False}
    write(ROOT/'results/final_status.json',status)
    text="""# 实验分析报告

ChronoFin「时证」——2026 犀牛鸟个人活动作品；任务1：AI应用与评判标准设计，金融分析方向。以下全部分数是项目诊断指标，不是腾讯评分。历史时间戳使用进程实际UTC时间。

## 主要结果

作品已从规则与模板原型发展为金融研究工作台：真实 Hy3 生成、反证修订、可执行数字检查、原生财报引文、十维评估及评估器本身的验证。实验围绕生成质量、引用与计算约束、评估器稳定性和外部标签一致性展开。

同调用次数对照中，反证修订在15道后续题上比通用修订高5.339个项目诊断分，平均全流程tokens减少30.6%；公开人工标签的新响应验证中，三分类一致率由78%提高至90%。这些结果来自小样本、作者可见问题及同Hy3家族评判，适用范围和负结果在下文逐项列出。

## 完成范围与可核查分母

| 实验 | 完成/计划 | 统计单位和限制 |
|---|---:|---|
"""
    names={'brief_application':('主应用三方案','20题×3方案；不是60道独立问题'),'brief_meta':('原评估器变形','三份回答的受控变形/重复'),'equal_call_application':('同调用预算/初稿消融','复用20题初稿，四种处理；有新修订与新判定'),'order_judgments':('裁判顺序稳定性','6份固定答卷×2裁判×4处理'),'external_human_v3':('外部人工标签验证','300条响应记录×2判据，150个问题；含150条旧判定复用'),'semantic_stress':('金额与语义压力测试','30个人工构造对照项×2裁判'),'native_pdf_v5':('原生PDF最终回归','5份官方PDF、12题；作者定义参考点'),'native_final_validation':('原生PDF固定裁判/变形','12个旧答卷复评＋18个最终答卷处理')}
    for k,(done,total)in planned.items():name,note=names[k];text+=f'| {name} | {done}/{total} | {note} |\n'
    text+=f'\n既定实验矩阵的缺失记录数：**{pending}**。历史失败保存在相应 attempt_history/resume_history 及旧版本；材料完整性与在线实验完成度分别校验。\n'
    text+="""
## 应用是否比合理基线更好

主实验共享Hy3/no_think/温度0/相同资料与截止日：词法top-8、全部可知资料单轮、来源扩展与反证修订两轮。15道后续题的原裁判均分如下；设计者见过所有题目，因此称作者回归集，不能称盲测。

| 方案 | 后续题均分 | 平均报告tokens |
|---|---:|---:|
"""
    for m in ['lexical','full_context','counterbrief']:
        x=app['strategies']['evaluation/'+m];text+=f"| {m} | {x['mean_score_failure_zero']:.3f} | {x['mean_tokens_reported']:.1f} |\n"
    text+="""
反证流程多一次调用，因此另设**同一完整资料初稿＋通用二次修订**对照，以及反证流程第一稿消融。全部由新的证据约束裁判重新评估，不能把新旧裁判分数混在一起。

| 同一裁判下的方案 | 后续15题均分 | 平均全流程tokens |
|---|---:|---:|
"""
    for m in ['full_context','counterbrief_first_pass','full_context_revision','counterbrief']:
        x=ground['application']['evaluation/'+m];text+=f"| {m} | {x['mean_score_failure_zero']:.3f} | {x['mean_pipeline_tokens']:.1f} |\n"
    d=ext['grounded_paired']['full_context_revision'];a=ground['application']['evaluation/counterbrief']['mean_pipeline_tokens'];b=ground['application']['evaluation/full_context_revision']['mean_pipeline_tokens']
    text+=f"\n反证流程相对同调用次数的通用修订平均提升 **{d['mean_difference']:.3f}分**，来源组bootstrap95%区间 [{d['source_group_bootstrap95'][0]:.3f}, {d['source_group_bootstrap95'][1]:.3f}]；平均报告tokens减少 **{(1-a/b)*100:.1f}%**。只有6个来源组且跨来源题与其他组重叠，区间只是探索性统计。新裁判把反证均分从原来的97.328降到91.861，也说明单裁判高分不能当作真实正确率。完整逐题胜负、门禁与初稿见 results/grounded/v1。\n"
    text+="""
## 评判标准是否有判别力、一致性与抗攻击能力

主变形验证的12个有害样本全部低于原答卷，6个等价变形均未出现超过5分变化，3个纯篇幅包装没有超过5分增益。四类有害处理是伪引用、遗漏重要反证、无据因果结论和评分注入；不是所有攻击的安全认证。

原裁判曾把正确的“1.55 billion USD = 15.5亿美元”判成十倍错误，D01逆序后从100降为55。没有改写该历史判断。加入Decimal金额见证后，对6份答卷的同序、逆序、固定乱序和重复共48次比较如下。

| 裁判 | 平均观测极差 | 最大极差 | 极差>5的答卷 |
|---|---:|---:|---:|
"""
    for m,x in ext['order_reliability'].items():text+=f"| {m} | {x['mean_range']:.3f} | {x['max_range']:.1f} | {x['range_over5']}/{x['n_answers']} |\n"
    text+="""
金额见证只证明数值等价，不能证明公司、期间或预测属性。另构造6种金额表达，各有等价、十倍错误、期间错误、主体错误、预测当事实五种状态。旧裁判30项答对24项，金额等价仅接受2/6，并漏过2个十倍错误；约束裁判30/30，接受6/6等价并拒绝24/24错误。这是30个合成压力项，不能外推为真实财务准确率100%。

## 与已发表人工标签是否一致

使用[FinanceBench官方公开数据与结果](https://github.com/patronus-ai/financebench/tree/cc39aeb4afdf33909ee1412188bf89035950c2eb)，人工标签来自原作者，不是本项目新招募标注员。公开150题中每题按哈希选一个历史回答为开发记录，后再从剩余文件固定选一个新回答记录验证。标签不进入Hy3提示。历史GPT/Claude回答来自公开数据，本项目没有调用这些模型。

早期实验有两项负结果：复杂检查清单未优于简洁判据；95%左右的模型自报信心也不能保证正确。还发现当前主数据参考答案与历史标签所依据参考版本不同，v2起绑定到标签同一记录的gold_answer。开发分歧中，模型把答非所问的长篇内容误判为“拒答”；v3明确要求拒答必须有拒绝/无法确定的表达，答非所问归为错误。协议冻结后在新选响应记录上验证。

| 新回答验证，150条 | 三分类一致率 | Macro-F1 | Cohen κ |
|---|---:|---:|---:|
"""
    for m in ['holistic_v2','operational_v3']:
        x=human['groups']['new_response_validation/'+m];text+=f"| {m} | {x['accuracy_failure_wrong']*100:.1f}% | {x['macro_f1']:.3f} | {x['cohen_kappa']:.3f} |\n"
    h=human['paired']['new_response_validation'];text+=f"\n配对一致率提升{h['mean_accuracy_difference']*100:.1f}个百分点，按32个公司聚类bootstrap95%区间 [{h['company_bootstrap95'][0]*100:.2f}, {h['company_bootstrap95'][1]*100:.2f}]。原始输入哈希复核确认两组没有完全相同的回答字节。新回答共享原问题与公司，且基准公开，不能称未知公司盲测或排除预训练污染；仍有15/150条与人工标签不一致。此实验仅验证正确/错误/拒答分类，**没有验证开放式十维评分的全部专家一致性**。\n"
    text+="""
## 原生PDF是否实际可用

五份原件为Meta FY2024、Amazon FY2024、NVIDIA FY2025 CFO说明、Apple FY2025 Q4报表和腾讯2025Q2中文业绩；三份新来源在资料卡主实验冻结后引入。固定12题，包括两个披露日前拒答、前瞻当事实、GAAP/调整口径、现金与利润分化及地区/产品线反证。原件URL、页码、日期、SHA-256和任务参考点均提供。

v1短ID接口错误造成2/3失败；v2能完成12项但空数值登记和引文复制造成误算/遗漏；v3数值反馈改善，严格引用检查又暴露4项结构/判定失败。这些旧行保留，没有用成功子集掩盖失败。

v4加入原文行区间但仍暴露自由公式单位错误；最终v5进一步用类型化比例、增长、差额和单位转换，由程序编译公式并反馈Hy3修订。最终v5由Hy3选择原文行区间，程序截取原句；由Hy3评判选择候选句ID，程序绑定候选原话。行号绑定证明引句身份，财务语义仍由独立的原文审计判断。模型初稿、修订、抽取结果及每次评判均保留。没有把原答卷改写成引文来制造正确率。

| 最终v5案例 | 状态 | 项目诊断分 |
|---|---|---:|
"""
    for x in native.get('records',[]):text+=f"| {x['id']} | {x['status']} | {x.get('score','未测')} |\n"
    if nv:
        x=nv['fixed_judge_comparison'];text+=f"\n为避免‘换了评委所以分数变高’，另用同一v5裁判复评全部v2旧答卷：配对{ x['n']}题，v5−v2均分差 {x['mean_v5_minus_v2']:.3f}，胜/平/负为 {x['wins']}/{x['ties']}/{x['losses']}。最终答卷的9个有害变形中{nv['harmful']['strict_score_drops']}个严格降分；9个重复/等价处理中{nv['equivalent_and_repeat']['absolute_change_over5']}个变化超过5分。完整失败和差异见 results/native_validation/v2。\n"
    text+="""
最终v5仍有实质缺陷：AP02把同一F13/F14分别重复作为跨期输入，得到0%且在文字中承认无效，诊断仍为92.971；TC03部分金额正文没有完整绑定对应资料，最终因反证缺失封顶65。界面另加可见复核提示，不提高或重写原分数。这证明类型化算术与高评分仍不能代替财务语义审查。

这些是迭代后的同题回归，不是独立泛化成绩。文字PDF可用，扫描OCR、复杂跨页合并表、重述版本与未知报告首次公开时间仍受限制。未登记原件的日期由用户声明，不能声称自动发现真实首次公开时间；日级截止也不处理同日盘前盘后。

## 调用规模、复现与交互验证

"""
    text+=f"按供应商请求哈希去重，保存的成功调用至少 **{usage.get('unique_successful_request_traces',0):,}次**，输入{usage.get('input_tokens',0):,}、输出{usage.get('output_tokens',0):,}tokens。此统计是保存记录可核实的下界，不含无usage失败及早期未保全的中间响应；复用答卷不重复计数。\n"
    text+="""
真实浏览器已验证保存结果、引用跳转、十维展示、下载、错误清理；另完成腾讯中文PDF上传→Hy3抽取/生成→原文支持审计，以及实时自定义问题。最终第一次自定义问题验收因裁判limitations格式失败，记录保留在audit/live_history/v5_first；修正空参考协议并重新实际通过，失败期间部分中间模型响应未回传保存，计费汇总不包含它们。没有独立参考清单的实时问题不显示总分，重要信息覆盖、反证完整性与未知边界保持未测。证据见 audit/ui_live_verification.json 及相应模型原始记录。

确定性离线复算使用保存的语义判断，不能证明该判断正确。最终全量测试、冻结协议核验、无密钥无原件缓存的临时副本复现见 audit/final_tests.log、artifact_verification.json、clean_checkout_verification.json。临时副本使用同机解释器；没有冒充第三方复现或Docker验收。早期brief v1格式失败和native v1两项失败未完整保全中间响应，已如实保留错误和此缺口。

![同调用次数对照](../assets/figures/application_comparison.png)

![外部标签与顺序稳定性](../assets/figures/reliability_and_completion.png)

![同一最终裁判的原生PDF对照](../assets/figures/native_same_judge.png)

## 基线比较与研究限制

原项目121项测试与离线好/中/差100/55/40实际通过。no_think和默认high的新鲜腾讯原PDF试验均得到披露前unanswerable、原诊断55；披露后partial、原诊断20。规则对槽位及可回答性的封顶较严格，不能只凭20断言Hy3完全不懂财报。原项目与本项目资料、任务、评估器均不同，不把20对比97称作公平准确率提升。

本次优势是研究流程可用、原稿透明、相同调用预算对照、原始财报接入、十维判据以及对评委的误判/顺序/金额/外部人工标签验证。多维金融评估、claim拆分与反证都已有公开先例；贡献是有针对性的组合、片段绑定和经真实失败推动的可复现验证，不声称领域首创或超越论文榜单。

当前研究限制包括：开放式样本较小；生成与评判共用Hy3家族；仍有语义误判、无效跨期输入和回归低分；尚无新增财务专家盲标及研究员试用；复杂长年报与重述数据覆盖不足。逐题原始输出、错误归因和复核提示随实验提供。外部FinanceBench结果验证的是正确/错误/拒答三分类，不能替代十维开放式评估的专家一致性。
"""
    (ROOT/'docs/最终实验分析报告.md').write_text(text)
    print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
