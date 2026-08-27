# ChronoFin「时证」研究版图与创新定位

> 检索与仓库审阅日期：2026-08-26（UTC）  
> 范围：腾讯犀牛鸟任务材料、Hy3 官方资料、公开论文与官方开源仓库，以及本仓库现有代码和结果。本文不是穷尽性系统综述；“新颖”均指在本次公开检索范围内的、可被实现和实验反驳的系统创新，不宣称世界首创。

## 1. 评审结论先行

ChronoFin 不应被包装成“更会写研报的财报 RAG”，也不应以“多个 Agent 分工写一篇投资报告”作为核心创新。前者已经有成熟的金融问答、混合检索、XBRL 数值查询和引用核验方案；后者已有完整的多 Agent 研究、估值与报告流水线。仅增加向量库、联网搜索、图表、DCF 或角色数量，最多是工程集成，不足以构成犀牛鸟“卓越作品”的差异化。

本项目最可信、也最有评审辨识度的主张是：

**ChronoFin「时证」是一套面向历史时点金融研究的可反事实审计系统：先以 point-in-time 边界限定当时可知的信息，再把来源、计算与结论编译为 typed proof graph，最后通过 causal metamorphic evaluation 验证“该变的结论是否按图变化、不该变的结论是否保持稳定”。**

三部分单独看都不是新概念；创新来自它们的闭环耦合：

1. **时间边界决定什么证据有资格进入图；**
2. **类型化证明图声明每个结论依赖哪些证据和计算；**
3. **受控变形用反事实输入检验这张依赖图是否真的约束了系统行为。**

这使产品从“生成一篇看起来合理的文字”转向“提交一组可验证的研究承诺”。

## 2. 与任务及 Hy3 的契合

[犀牛鸟任务 PDF](../../tasks/%E7%8A%80%E7%89%9B%E9%B8%9F%E5%BC%80%E6%BA%90-%E5%AE%9E%E6%88%98%E4%BB%BB%E5%8A%A1-%E6%B7%B7%E5%85%83%E5%A4%A7%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B%E9%A1%B9%E7%9B%AE.pdf)要求开放应用同时给出自定义评测，覆盖至少约 5 个可操作维度，说明样本来源与难例，并至少验证评测器的**区分度**和**一致性**；还鼓励测试冗长、术语堆砌、伪引用等对抗行为。ChronoFin 的差异化恰好同时落在“应用”和“评测”两侧，而不是把评测当附录。

[Hy3 官方仓库](https://github.com/Tencent-Hunyuan/Hy3)与[中文说明](https://github.com/Tencent-Hunyuan/Hy3/blob/main/README_CN.md)把长上下文、推理、Agent/工具调用和金融建模列为重要能力。ChronoFin 中 Hy3 负责开放问题规划、跨段落语义归一、事实/派生/推断类型化及结构化答案生成；时间过滤、来源身份、公式执行和硬门禁则由确定性代码掌权。这种分工既能体现 Hy3 的不可替代价值，又不会把模型当作自身答案的唯一裁判。

需要强调：项目使用的是 Hy3 推理与结构化生成能力，不涉及训练或微调；这符合任务边界。

## 3. 公开研究与项目版图

### 3.1 财报问答、RAG 与确定性数值查询已经成熟

| 代表工作 | 已覆盖能力 | 对 ChronoFin 的创新下限 |
|---|---|---|
| [FinanceBench](https://github.com/patronus-ai/financebench) | 基于公开公司财报的问题、答案和证据定位，用于金融 RAG/问答评测 | “上传财报—问问题—给出处”已经是基线能力 |
| [FinQA](https://github.com/czyssrs/FinQA) / [论文](https://arxiv.org/abs/2109.00122) | 财报数值推理、程序化计算与证据 | “让模型列公式并算数”不是新的产品命题 |
| [SEC RAG Platform](https://github.com/adwitiyashukla/sec-rag-platform) | 混合检索、XBRL 确定性数值引擎、groundedness 校验和回归测试 | 普通混合 RAG + XBRL + 引用检查仍不足以区分 |
| [SEC EDGAR API 官方说明](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 无需 API Key 的 submissions 与 XBRL company facts 数据 | 可复现的公开财务事实抓取已有官方基础设施 |
| [Arelle](https://github.com/Arelle/Arelle) | XBRL 处理与校验 | 生产级项目应复用标准解析器，而非把 PDF 抽取本身当创新 |

SEC 还明确说明 EDGAR 的 HTML/纯文本申报版本才是官方申报文本，XBRL 不应成为唯一决策证据，见 [About EDGAR](https://www.sec.gov/edgar/searchedgar/aboutedgar.htm)。因此合理的架构是：XBRL 用于确定性计算和交叉核对，最终 claim 仍链接到官方可读原文，而不是把结构化数值当作无条件真值。

### 3.2 多 Agent 研报与估值流水线不是空白地带

| 代表工作 | 已覆盖能力 | 对 ChronoFin 的创新下限 |
|---|---|---|
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 多 Agent 金融研究、数据源协作、估值模型、图表与多章节报告 | “研究员/估值师/审稿人多个 Agent 写研报”高度同质化 |
| [Microsoft Finance Agent Benchmark](https://github.com/microsoft/FinanceBenchmark) | 金融研究与业务简报任务、rubric assertion 与 LLM judge | 仅展示 Agent 能完成任务，不等于评测可靠 |
| [Big Finance Benchmark](https://github.com/Rogo-Technologies/big-finance-benchmark) | 工作流驱动的金融问题、专家 rubric 与工具评测框架 | 需要展示任务级验证，而非一两个漂亮案例 |
| [FinanceGym](https://financegym.github.io/) | 强调 point-in-time 数据的金融深度研究评测 | “历史时点”本身不是无人触及的关键词，必须把机制和评测做深 |

因此，普通多 Agent 方案存在三个评审问题：角色只是提示词、错误会在 Agent 间传播、最终仍由另一模型对整篇文章打一个不可审计的分数。角色数量不等于技术深度。

### 3.3 金融报告与 Agent 评测正在快速走向细粒度、可追溯

| 代表工作 | 重点 | ChronoFin 仍需超过的基线 |
|---|---|---|
| [腾讯 finLLM-Eval](https://github.com/Tencent/finLLM-Eval) | 以 Agent-as-Judge 检查金融事实准确性与逻辑一致性 | “事实 + 逻辑的 LLM 裁判”本身不能作为腾讯赛道中的独有创新 |
| [FinReportBench](https://arxiv.org/abs/2608.04374) | 面向机构级金融报告生成的细粒度专家 rubric | 报告质量必须拆成可解释维度，不能只报均分 |
| [TieOutBench](https://github.com/DimaMerc/TieOutBench) | gate + weighted rubric、数字追溯与金融工作流核对 | 数值 lineage 和硬门禁已成为可信金融系统的重要方向 |
| [Fin-RATE](https://arxiv.org/abs/2602.07294) | 单实体、跨实体和纵向追踪，暴露期间/实体错配与幻觉 | ChronoFin 必须严肃处理 entity-period-unit 语义，而非只匹配数字 |
| [KPI extraction from filings and earnings calls](https://arxiv.org/abs/2605.03147) | 财报与电话会 KPI 抽取、专家标注 | KPI 提取或管理层指标追踪可作为任务，不足以单独构成创新 |
| [AuditAgent](https://arxiv.org/abs/2510.00156) | 跨文档审计证据发现与多 Agent 分析 | “跨文档找风险”已有相邻方案，必须提供更严格的时点和因果验证 |
| [IC Memo Copilot](https://github.com/alexanderpersson3/ic-memo-copilot) | claim ledger、引文存在性和语义核查 | citation-first 写作已出现；ChronoFin 的差异必须来自时间约束与反事实测试 |

共同趋势很清楚：金融生成系统正在从“答案像不像”走向“每个事实、公式、期间和来源能否核对”。ChronoFin 若只宣传引用或证明图，会与这些工作重叠；必须展示三元闭环。

## 4. 为什么明确否决两个常见方案

### 4.1 否决“普通财报 RAG”作为主方案

一个典型方案是上传 10-K/年报，切块入库，由模型回答并附页码。它适合做 ChronoFin 的**对照基线**，不适合做核心参赛贡献，原因是：

- 用户和方法已经被 FinanceBench、FinQA、SEC RAG 等充分覆盖；
- 一个 URL 或页码存在，不代表引文蕴含该 claim，也不保证实体、财期、币种和单位一致；
- 若先检索后判断发布日期，未来年报可能已经进入提示词，即使最终回答没有显式引用也形成污染；
- 对同一问题换一个证据叶节点，普通 RAG 没有形式化预期说明哪些结论应该改变；
- demo 容易变成“又一个聊天框”，难以在两分钟内让评委看到技术不可替代性。

### 4.2 否决“多 Agent 自动研报”作为主方案

一个典型方案是让宏观、行业、财务、估值和风控 Agent 分工，再由总编 Agent 汇总。它同样可作为产品外壳或基线，但不能成为创新核心，原因是：

- FinRobot 已经覆盖多 Agent 研究、估值和长报告；
- 大量“角色”通常共享同一模型和同一不可靠数据边界，相关错误不会因投票自动消失；
- 文章更长、术语更多反而可能欺骗 LLM judge，正属于任务要求警惕的评测攻击；
- 没有 claim-level 依赖与确定性计算时，无法定位错误究竟来自来源、检索、公式还是推断；
- 研报文采和篇幅会掩盖未来信息泄漏、伪引用和期间错配等致命错误。

## 5. ChronoFin 三元闭环的可检验新颖性

### 5.1 Point-in-time：从“回答日期”升级为“证据可用性边界”

对截止日 \(t\)，系统先构造可用证据集：

\[
\mathcal{E}_t=\{e\mid published\_at(e)\le t\}
\]

过滤发生在检索和模型调用之前；截止日后的文档不能进入提示词，并进入可见的隔离日志。相同问题在披露前应回答“不可知/部分可答”，披露后才转为可答。这里的目标不是训练数据层面的“知识截止日”，而是**每次研究任务可审计的数据可见性**。

仓库中 [retrieval.py](../src/chronofin/retrieval.py)执行日期过滤，[pipeline.py](../src/chronofin/pipeline.py)把排除文档和 eligible/retrieved chunk 写入 provenance。模型给出的来源日期、页码和实体不会被信任，而是从本地 registry 回绑；这是一条重要的信任边界。

### 5.2 Typed proof graph：从“附几个引用”升级为“提交依赖关系”

当前图包含 `source / calculation / claim` 节点以及 `supports / operand_of / derives` 等有向边；claim 还区分 `FACT / DERIVED / INFERENCE / UNKNOWN`，并携带 entity、period、unit、known_at 和 semantic key。图必须无悬空关键边、派生结论必须有计算边、计算必须有来源绑定，且整体无环。

这比普通 citation list 多出三类可执行承诺：

- **身份承诺**：引文必须属于被检索到的确切 chunk，模型不能自报来源元数据；
- **数值承诺**：公式可在受限表达式解释器中重算，叶数值能回到原文；
- **语义承诺**：每个输出指标有稳定 semantic key，便于跨运行和反事实比较。

实现见 [models.py](../src/chronofin/models.py)、[proof_graph.py](../src/chronofin/evaluator/proof_graph.py)、[numeric.py](../src/chronofin/evaluator/numeric.py)和[ontology.py](../src/chronofin/ontology.py)。需要诚实说明：`RUBRIC` 节点类型虽已定义，当前 `from_answer` 实际只构造 source、calculation 和 claim；`contradicts/requires` 等边也尚未形成完整产品闭环。因此现状应称“类型化证明图 v0.1”，不应宣传为成熟知识图谱或完整规则引擎。

当前事实信用也采用保守边界：没有 semantic judge 时，FACT 只有逐字 evidence span、DERIVED 只有安全执行结果的 canonical projection 可以得分，INFERENCE 不靠词面相似自动通过；lexical overlap 只作为诊断字段。摘要必须逐句绑定 claim ledger，caveat 则是确定性政策投影。这提高了可审计性，但也意味着系统没有证明同义改写的语义蕴含能力。

### 5.3 Causal metamorphic evaluation：从“静态打分”升级为“干预后行为测试”

“causal”在这里特指**系统输入—输出依赖的干预测试**，不是对企业经营因果关系的计量识别。做法是对已知证据叶节点施加受控变形，用证明图的后代集合生成预期：

- 后代结论应按 oracle 发生正确改变，记为 causal key response（CKR）；
- 非后代结论应保持不变，记为 locality；
- 二者的调和平均为 causal fidelity。

此外，当前压力集有 36 类 label-changing 变形：除伪引文、未来来源、错误实体/期间/单位/计算外，还覆盖 citation date/URL 身份、`known_at` 缺失或错配、query entity/period/metric、source/operand 单位、claim 极性和中文数字、摘要与 caveat 侧信道、UNKNOWN 肯定化，以及用无关负面句、跨句拼接或“已有目标证据仍拒答”绕过拒答审计等；排序/空白格式两类属于 label-preserving 变形。合格评测器既要对前者降分，也不能对后者乱降分。实现见 [mutations.py](../src/chronofin/evaluator/mutations.py)和[core.py](../src/chronofin/evaluator/core.py)。

这解决了静态 rubric 的核心盲区：一份答案即使碰巧正确，也未证明系统使用了正确证据；只有当证据改变后，相关结论正确响应且无关结论稳定，才获得更强的依赖忠实性证据。

### 5.4 三者为什么缺一不可

| 缺失部分 | 系统退化为何物 | 仍然无法回答的问题 |
|---|---|---|
| 无 point-in-time | 带引用的财报问答 | 这些事实在当时是否已经公开？ |
| 无 typed proof graph | 有日期过滤的文本 RAG | 哪个来源/公式支撑哪个结论？ |
| 无 causal metamorphic evaluation | 静态可追溯报告 | 依赖图是有效约束，还是事后装饰？ |

本次公开检索没有发现把这三者作为同一产品主交互、同一评测对象和同一可运行闭环的直接等价项目；但这只是**检索范围内的组合创新判断**。项目应持续做 prior-art 更新，不应使用“全球首个”等不可证伪口号。

## 6. 当前仓库的证据与证据边界

| 已有证据 | 当前结果 | 可以说明什么 | 不能说明什么 |
|---|---:|---|---|
| [离线合成实验](../results/offline_experiment.json) | good/medium/bad 为 100/55/40；36 个破坏性变形均被降分，2 个不变性变形均未降分；严重度与降分 Spearman≈0.424 | 评分规则在这一个受控夹具上能识别包括摘要/caveat、UNKNOWN、query 对齐和拒答侧信道在内的预定义错误 | 不等于跨公司、跨格式、真实开放问题上的泛化，也不是人工一致性；严重度标签未经专家校准 |
| [多簇形式化压力集](../results/synthetic_benchmark.json) | 8 家虚构公司、72 个原题、每题 36 个破坏性 + 2 个等价变形，共 2,736 runs；36 类破坏召回均为 1，PDA=1、IVR=0，严重度—降分 Spearman=0.423556 | 当前确定性评估器在完整可见模板矩阵上能检出预定义错误，且两阶段 cluster bootstrap 保留每题全部 38 个相关变异 | 不是 held-out、没有专家标签，退化 CI 不代表真实世界零不确定性；严重度未由专家校准 |
| [四策略组件消融](../results/evaluator_ablation.json) | 同一 2,736-run 矩阵上，plain、精确引用、时点+引用、完整系统的破坏检出率为 0%、5.56%、13.89%、100%；4 策略共 10,944 outcomes，IVR 均为 0 | 能定位精确引用、时点过滤与完整图/数值/拒答/可见投影门禁在受控攻击上的增量 | 是 evaluator 能力消融，不是 Hy3 问答基线或外部强模型对比 |
| [Point-in-time 消融](../results/offline_experiment.json) | 严格检索未来 chunk 数 0；关闭过滤后为 3 | 过滤位置确实能阻断构造的未来年报诱饵 | manifest 日期可能标错；未覆盖修订稿、时区和盘中可用性 |
| [真实腾讯年报前后对照](../results/public_tencent_after_publication_final_score.json) | 2025-12-31 前对 FY2025 全年数据拒答并隔离 2026-04-09 年报；2026-04-10 后可答；当前两份答案各确定性重算 5 次均为 100 且 scorecard hash 完全一致 | 产品主叙事已在一个真实官方披露链上跑通，当前答案字节与当前确定性 evaluator 重复一致 | 只有一家企业和一个问题族；无模型调用/语义蕴含判断，内部评分不是专家真值 |
| [三公司挑战历史记录与当前回归](postfreeze_challenge_report.md) | 四个数据文件不变；仓库内历史 v1 为 3/6→6/6；当前加固 evaluator 上的 seen regression 为 0/6→6/6，并拒绝 3/3 future-leak 负例 | 数据、历史结果、当前 evaluator/adapter 与当前前后结果分别入账；两条失败—修复链可复核 | 历史链无外部可信时间戳且首轮完整 evaluator 身份不可证；当前链已见数据，不是 post-freeze/held-out 或新鲜 Hy3 准确率 |
| [当前因果重处理](../results/live_causal_experiment_current.json) | 当前确定性层重绑定两份历史 Hy3 保存答案；合成叶节点 144→180 后净利润和净利率正确更新，CKR/locality/fidelity 均为 1.0，前后 score 均为 100 | 输入哈希绑定的当前重处理在该受控单例中符合图预期 | 本次未调用模型，不能冒充当前 Hy3 在线生成；单个手工 oracle 不能估计总体因果忠实度 |
| [历史 Hy3 生成记录](../results/live_stability.json) | 历史 3 次得分均 100，语义键 pairwise Jaccard 均值 0.889，未来泄漏 0 次 | 保留的历史运行在该合成任务上的关键数值较稳定 | 三次样本太少，且未重新绑定当前 projection/evaluator，不能称为当前生成稳定性 |
| [历史 Hy3 语义裁判记录](../results/public_tencent_semantic_stability_final.json) | 补全表头与指标上下文后，历史 5 条 claim × 3 次均为 supported、增强分数 100/100/100；修复前 0.20 的失败版本仍保留 | 保留的历史 prompt/trace 中存在一条可审计的协议修订记录 | `evaluation_scope=historical_answer_projection`，历史答案字节未独立封存且不绑定当前 projection；不能称为当前稳定性、外推跨问题或替代人工专家 |
| [干净环境复现](../results/cleanroom_verification.json) | 无 API Key、禁网、临时 checkout/新 venv 中离线测试、实验、回归、CLI、Git staging 与 submission verifier 全部通过，缓存 PDF 为 0 | 已提交的离线链路不依赖本机缓存财报或秘密环境变量 | 新 venv 继承当前主机 build tooling；不是第三方操作系统复现或在线 Hy3 重放 |

公开腾讯数据来自[腾讯投资者关系财务报告页](https://www.tencent.com/investors/financial-reports/)；仓库只保存下载清单和来源 URL，不把受版权保护 PDF 当作自有数据集再分发，见 [tencent_sources.json](../data/public/tencent_sources.json)。

## 7. 可主张与不可主张

### 可以主张

- 在本次公开检索范围内，ChronoFin 把 point-in-time、typed proof graph 和 causal metamorphic evaluation 组合成了一个差异明确、可运行、可反驳的金融研究闭环。
- 当前原型已经实现检索前时间过滤、来源元数据回绑、精确引文与计算血缘、硬门禁、36 类破坏性/2 类不变性变形，以及对两份历史 Hy3 保存答案的当前因果重处理。该重处理不是一次新的在线模型调用。
- 产品核心不是预测股价或给出买卖建议，而是提高历史研究的可知性纪律、证据透明度与故障定位能力。

### 不可以主张

- 不可称“世界首创”“生产级”或“已经超越所有金融 Agent”；本次检索不是系统综述，也没有统一 benchmark 对比。
- 不可把 causal fidelity 说成企业经营因果推断；它只度量系统对受控证据干预的响应忠实性。
- 不可把合成单例的 100 分、PDA=1 或 causal fidelity=1 当作真实世界准确率。
- 不可把同族 Hy3 语义裁判当作人工专家；保留的 15/15 supported 只是历史 answer projection 上的记录，未绑定当前答案字节；修复前 20% 的逐 claim 完全一致率也说明结果对证据呈现与协议敏感，需要跨模型校准和人类标注。
- 不可声称彻底消除未来泄漏；手工 `published_at`、修订/重述、网页先于正式 filing、时区和缓存都可能破坏时间真值。

## 8. 最有价值的后续研究问题

1. 在 6–10 家企业、多个财年和至少 60–80 个 held-out 问题上，三元闭环是否仍优于普通 Hy3 RAG、RAG + 精确引用、以及只用 LLM judge 的评测？
2. 对未来泄漏、财期错位、实体混淆、币种/单位变化、GAAP/非 GAAP 混用、修订年报和伪引文进行簇级变形后，PDA、不变违规率和 bootstrap 置信区间如何？
3. 双专家独立标注的 point-in-time 合规、引用蕴含和 material nugget 覆盖能否达到可接受一致性，并与自动评测达到 Spearman/Kappa/ICC 的预设阈值？
4. 将 rubric/requirement 真正纳入证明图后，能否把“遗漏关键结论”也转化为可解释的缺失路径，而不是只看输出结构？
5. 在真实披露时间戳、修订链和可复现 snapshot 上，系统能否区分“报告期”“发布日期”“首次可得时间”和“修订生效时间”？

只有这些问题得到跨样本、跨公司和人工校准的回答，ChronoFin 的组合创新才会从强原型升级为“卓越作品”级证据。
