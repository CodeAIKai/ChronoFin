# ChronoFin 人工标注与一致性验证协议

> **状态：尚未执行（not started）。** 截至本文档编写时，项目尚未完成标注员招募、培训、正式标注、独立复标或一致性计算。仓库中现有 `results/` 均不是人工标注结果。本文档是待预注册的执行协议，不能据此声称“专家一致率”“人类水平”“human agreement”或“人工验证通过”。

当前应公开填写为：

| 字段 | 当前值 |
| --- | --- |
| `human_annotation_status` | `not_started` |
| 已招募标注员 | 0 |
| 已完成正式样本 | 0 |
| 独立人工 labels | 0 |
| adjudicated gold | 0 |
| human-human agreement | `N/A — not measured` |
| human–LLM agreement | `N/A — not measured` |

## 1. 目标

人工研究用于回答三个问题：

1. claim、citation、材料完整性和推断边界的自动/LLM 判定是否与金融专家一致；
2. 十维分数和硬门禁能否定位专家认为的材料性错误，而不是只偏好文风；
3. PDA、IVR、CKR 和 Locality 在自然回答与受控变形上的判定是否有效。

人工标注不是用来重做可由代码精确判断的算术或时间比较。确定性结果会展示给 adjudicator 复核，但不能被单个主观评分静默覆盖。

## 2. 标注总体设计

### 2.1 Cluster 与抽样单位

一个独立 cluster 定义为同一：

`question × entity × as_of_date × frozen source snapshot`。

同一 cluster 下可包含：原始回答、不同系统回答、destructive contrast、label-preserving variant 和 source-level causal rerun。所有统计划分必须按 cluster 完成，不能让同一 base case 的 mutant 跨训练、校准和测试集合。

正式样本量、领域比例和 power analysis 必须在 pilot 后预注册；在这些数字冻结和实际完成前，不报告任何计划数为已完成数。抽样至少应覆盖：

- `answerable / partial / unanswerable`；
- FACT、DERIVED、INFERENCE、UNKNOWN；
- 单期、跨期、跨公司、IFRS/non-IFRS、币种/单位换算；
- 正确回答与伪引文、错期间/实体/单位、错计算、材料遗漏、injection；
- label-preserving 的顺序、格式、同义改写和等价算式；
- source mutation 的后代变化与非后代稳定。

### 2.2 标注员资格（计划）

每个正式项目应由至少 3 名相互独立的金融、会计、审计或证券研究背景标注员处理。每名标注员须：

- 能理解任务语言和原始披露语言；
- 通过包含期间、口径、单位、表格和拒答案例的资格测试；
- 声明与被评公司、系统或模型供应商的利益冲突；
- 在独立阶段不得讨论答案或查看其他标注员意见。

标注员的真实人数、资历分布、报酬、退出和排除情况必须在实际执行后如实填写；本文档不预填虚构信息。

### 2.3 盲化材料包

每个标注包包含：

- query、entity、requested period、as-of date；
- 截止日当时冻结的 source snapshot 及文档目录；
- 候选回答、原子 claims、citation spans、calculations 和 proof graph；
- 确定性执行器生成的只读 identity/time/arithmetic audit（主标注阶段可分屏显示，不能包含总分）。

必须隐藏：模型/系统名称、prompt、生成成本、自动总分、是否为 mutation、其他标注员意见和预期排名。候选顺序随机化；若进行 pairwise preference，A/B 顺序在标注员间平衡。

标注员只能使用冻结材料包，不能用搜索引擎或模型参数知识补充截止日后的信息。发现 source snapshot 不足时选择 `indeterminate/source_missing`，不得猜测。

## 3. 在看到系统输出前构造 gold nuggets

材料完整度不能从候选回答反向生成。计划流程为：

1. 独立专家只看 query 和 frozen sources，提出最小、原子的必答 nuggets；
2. 另一专家检查每个 nugget 是否在截止日前可回答、是否重复、是否包含错误口径；
3. adjudicator 在不看候选回答的条件下冻结 nugget 文本、稳定 semantic key、可接受同义表达和材料性权重；
4. 冻结后才允许打开候选回答。

材料性等级采用预定义序数：

- 3：缺失会改变核心结论、估值/风险判断或 answerability；
- 2：重要但不单独改变核心结论；
- 1：补充背景。

若无法可靠区分，统一等权；不得让 LLM 在看过答案后调整权重。MCR 的分母必须包含所有冻结 nuggets，包括候选系统均未覆盖的项目。

## 4. 原子标注表

### 4.1 任务与 answerability

首先标注：

- `task_valid`：`yes / no / indeterminate`；
- `answerability_gold`：`answerable / partial / unanswerable / indeterminate`；
- 截止日前是否存在足够证据；
- 回答是否越过 as-of date，是否把单季/半年外推为全年。

对于 UNKNOWN，人工必须评价“不可知结论是否被现有及缺失证据合理证明”。当前自动 `factual_support` 跳过 UNKNOWN，此人工标签应单独保存，不得丢弃。

### 4.2 Claim 标签

每条原子 claim 记录：

- `claim_type_gold`：`FACT / DERIVED / INFERENCE / UNKNOWN`；
- `verifiable`：`yes / no / indeterminate`；
- `citation_worthy`：`yes / no`；
- `materiality`：1/2/3；
- `support_label`：
  - `supported`：给定证据完整蕴含命题，实体、期间、口径、单位一致；
  - `partial`：仅支持命题的一部分，或缺少不改变主体但不可忽略的限定；
  - `unsupported`：证据没有提供足够支持；
  - `contradicted`：证据明确与命题冲突；
  - `indeterminate`：source 缺失、任务歧义或多个标签均合理。
- `error_tags`：可多选 `entity / period / unit / currency / metric_definition / sign / rounding / source_missing / unsupported_inference / other`；
- 一句基于 source 的理由和对应 span。

不得因为答案长、流畅、有表格、粗体或专业语气而提高 support 标签。

### 4.3 Claim–citation 对

每个 `(claim, citation)` 对独立标注：

- identity 和 exact-substring：由确定性层预填 `pass/fail`；人工只在 registry/解析明显错误时提出 challenge；
- semantic relation：`full_support / partial_support / irrelevant / contradicts / indeterminate`；
- `source_quality`：`primary / secondary / unknown`；
- `temporally_valid`：确定性预填；
- 引文是否越过证据边界、是否把相邻列/年份错误归属给 claim。

一个 claim 有多条 citation 时，先逐条标注，再判断它们的并集能否完整支持 claim。CitPrec 使用逐对结果，CitComp 使用“至少一个或一个 citation 组合完整支持”的 claim 级结果；不能用 citation 数量代替正确性。

### 4.4 数值与计算血缘

对每条数值 FACT/DERIVED 记录：

- leaf 值是否逐项绑定正确 source、实体、期间、币种、单位和 scale；
- formula/operator 是否正确；
- 中间值和最终值是否按冻结规则重算一致；
- 舍入是否与 source 精度和回答展示精度一致；
- 输出值是否材料性错误；
- 若最终数值偶然正确但 leaf 或公式错误，标为 `reasoning_invalid`。

安全执行器结果是证据，不是不可挑战的最终标签；若 source table 解析或单位元数据错误，标注员应提交 registry challenge，由数据管理员修正后重新运行所有相关案例。

### 4.5 推断、风险与沟通

INFERENCE 单独标注：

- 所有明示前提是否 supported；
- 从前提到结论是否在金融语境中合理；
- 是否区分事实、推断与预测；
- 是否披露关键假设、反证和不确定性；
- confidence 是否与证据强度相称。

投资建议、安全和沟通记录：

- 是否出现买卖/仓位建议；
- 是否有充分且合规的支持与限定（当前自动正则不区分这一点）；
- 是否回显 prompt injection 或伪 grader 指令；
- 摘要是否忠实、清晰且没有掩盖 hard-gate 错误。

## 5. 人工标签如何映射到十维与规范指标

人工层不重新主观估计 source 日期或执行算术，而是为语义和材料性部分提供 gold。

| 维度/指标 | 人工提供内容 | 确定性内容 |
| --- | --- | --- |
| temporal integrity | registry challenge、披露/修订语义歧义 | published_at、known_at、cutoff 比较 |
| citation correctness / CitPrec | claim–span 的 full/partial/none/contradiction | identity、document/page、exact substring |
| citation completeness / CitComp | 哪些 claims citation-worthy、组合 citation 是否足够 | 是否存在有效绑定边 |
| factual support / WCP | claim support 标签、材料性权重 | claim 枚举、绑定元数据 |
| numeric lineage / NLA | 公式金融含义、材料性、registry challenge | 表达式执行、数值出现、graph trace |
| entity/period/unit | 歧义或特殊口径裁决 | 字段和文本规则匹配 |
| proof graph validity | 是否缺少语义依赖/反证边 | 缺节点、图环、结构边 |
| material completeness / MCR | 预先冻结 nuggets、权重和 coverage | semantic-key exact coverage proxy |
| inference boundary | 前提、推断合理性、caveat、confidence | claim type、是否有 evidence、置信度范围 |
| safety and communication | 建议是否有支持、风险披露、忠实摘要 | regex 和结构信号 |

WCP、MCR、CitPrec、CitComp 的公式严格采用 `docs/evaluation_method.md`。`partial` 在正式开始前必须预注册是 0.5 还是只用于分层报告；一旦冻结，不能根据系统排名修改。

## 6. 标注执行流程（计划）

1. **手册冻结**：用不进入正式集的示例讲解标签和边界。
2. **资格测试**：独立完成；阈值和排除规则在看到正式结果前冻结。
3. **Pilot**：所有标注员独立标注同一小批案例，用于发现手册歧义；pilot 不进入最终效果估计。
4. **协议修订并预注册**：冻结样本量、抽样、partial 映射、主要指标、CI 和排除规则。
5. **正式独立标注**：每项至少 3 人；不讨论，不展示模型或自动分数。
6. **锁定 pre-adjudication labels**：先计算 human-human agreement，保存不可变版本。
7. **Adjudication**：只处理分歧和 registry challenge，记录原标签、最终标签、理由和 adjudicator；adjudicated 标签用于 human–machine accuracy，不用于伪装更高的 IAA。
8. **盲复测**：预注册比例的重复项目用于 intra-rater consistency；重复项目不得相邻出现。
9. **发布**：输出数据版本、标注手册版本、人员统计、流失/排除、原始分歧和完整限制。

若标注员认为两个或多个标签均合理，应使用 `indeterminate` 或 response set，不强迫选择多数标签。该类样本单独报告，不在主结果中静默删除。

## 7. 一致性和 human–machine 指标

所有 human-human 指标必须在 adjudication 之前计算，并给 cluster-bootstrap 95% CI。

计划报告：

- nominal 标签（support、answerability、error tags）：Krippendorff’s α（nominal）；可附 Fleiss’ κ；
- ordinal 标签（材料性、分级质量）：Krippendorff’s α（ordinal）和 pairwise weighted Cohen’s κ；
- 若确实采集连续 response score：ICC(2,k)，不得以 Pearson/Spearman 代替一致性；
- evaluator 对 adjudicated claim labels：macro-F1、各类 precision/recall、confusion matrix；
- citation 和 hard-gate 检测：每类 sensitivity、specificity、false-positive rate；
- 排名任务：pairwise accuracy 和 Kendall’s τ-b；
- judge 有置信度时：Brier score、ECE、risk–coverage/AURC；
- 按 `indeterminate`、高/低人类分歧、语言、市场、claim type 和 mutation type 分层。

cluster bootstrap 单位必须是原始 `question × entity × as_of_date × source snapshot`，不能是单个 claim 或 mutant。具体采样算法沿用 `docs/evaluation_method.md`；报告 cluster 数、每 cluster 标签数、point estimate、seed、迭代数和 percentile CI。

任何预设的“可接受 α/κ”阈值都必须在 pilot 后、正式集之前冻结。本文档当前不填写阈值，也不把尚未产生的数值记为 0 或 1；正确表示是 `N/A — not measured`。

## 8. 变形测试的人工验证

自动 oracle 之外，人工验证分两种：

- **Evaluator contrast**：标注员独立判断原答案是否优于 destructive mutation；A/B 顺序平衡。与自动结果比较得到 human-backed PDA。
- **System causal mutation**：标注员核对 source mutation 是否自然有效、所有材料性后代是否列入 oracle、非后代是否确应不变。随后才计算 CKR、Locality 和 CausalFidelity。

label-preserving transformations 必须先由人工确认确实不改变答案含义；若变换造成歧义，应从 IVR 主分析中移除并记录原因，而不是按系统输出事后决定。

## 9. 质量控制和审计轨迹

- 每个 label 保存 `rater_id`（去身份化）、时间戳、handbook version、source snapshot hash 和理由；
- 对过快完成、缺理由、持续选择同一标签等行为使用预注册规则复查；
- registry challenge 由独立数据管理员处理，修复后对所有依赖案例统一重跑；
- 保留被排除样本及原因，报告排除前后结果；
- 标注员不能使用候选模型帮助标注；辅助工具若启用，必须单列人机协同条件，不能与纯人工结果混合；
- adjudicator 不能删除不方便的分歧，只能给出有 source 依据的决议或保留 response set。

## 10. 当前结果的正确表述

以下均**不是人工一致性**：

- `offline_experiment.json` 的确定性评估 20 次完全一致；
- `live_stability.json` 的 3 次 Hy3 生成分数一致；
- `public_tencent_semantic_stability.json` 的 judge 重复一致/不一致；
- synthetic mutation 的 PDA=1、IVR=0；
- 单个 causal case 的 CKR/Locality/CausalFidelity=1。

它们分别测代码确定性、模型重复稳定性或形式化 oracle 上的行为，不能写成“与金融专家一致”“达到 human-level”或“专家验证”。人工研究完成前，论文或演示应使用如下固定声明：

> 本项目尚未执行预注册的人类专家标注；当前结果来自确定性检查、合成/受控变形和模型重复实验，不提供 human-human 或 human–LLM agreement 证据。

正式执行后，应将本页顶部状态表替换为真实数字，并保留本历史版本，以便审计何时、由谁、按哪个协议获得结论。
