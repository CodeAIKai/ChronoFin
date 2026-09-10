# ChronoFin 开放式金融输出评估方法

> 适用版本：历史规则评估器及其确定性回归。当前开放式研究应用见[实验分析报告](最终实验分析报告.md)与[十维评估方法](开放式评估方法.md)。下文的“当前”指该历史阶段。

本文档定义 ChronoFin 当前评估器的计算口径、硬门禁、因果/变形指标和适用边界。除特别标为“规范指标”或“后续协议”的部分外，描述均以以下代码与配置为准：

- `configs/rubric.json`（`chronofin-rubric-v1.1`）
- `src/chronofin/evaluator/core.py`
- `src/chronofin/evaluator/{temporal,citation,numeric,proof_graph,semantic,mutations,benchmark}.py`
- `src/chronofin/{projection,summary,retrieval}.py`

最重要的解释规则是：**最终总分从属于可审计子指标和硬门禁；确定性检查优先于 LLM 语义判断。** 100 分只表示在本次输入、所启用的检查器和所提供的 gold 信息下没有检出错误，不等于专家认可、投资准确或生产安全。

## 1. 评估对象与记号

一次评估接收：

- 查询 `q = (question, entity, requested_period, as_of_date)`；
- 结构化回答 `A`，包含 `answerability`、摘要、原子 claims、evidence、calculations、caveats 和 provenance；
- 受信任的本地 chunk registry `R`；
- 可选的 gold nugget/`expected_semantic_keys` 集合；
- 可选、且应在看输出前冻结的 `expected_answerability`；
- 可选的 claim-level 语义判定 `semantic_verdicts`。

记：

- `C`：所有 claims；`C_v = {c ∈ C : type(c) ≠ UNKNOWN}`；
- `E`：回答中的 evidence；
- `P = {(c,e) : e ∈ c.evidence_ids}`：claim–citation 对；
- `K`：预先冻结的材料性 nuggets/semantic keys；
- `w_i, u_k > 0`：在看到被评回答之前冻结的 claim/nugget 权重；无专家权重时一律取 1，不允许 judge 临时发明权重；
- `J(A)`：评估器给回答 `A` 的 `final_score`。

底层引用/数值子检查仍可能用 `_mean(..., default=1.0)` 表示“没有待检查对象”；但 v1.1 不再允许据此让空答案通过。`answerable` 必须有非 UNKNOWN claim，`partial` 必须同时有实质 claim 与 UNKNOWN claim，`unanswerable` 必须有 UNKNOWN claim。若提供 answerability oracle，输出标签必须匹配；未提供 oracle 的拒答还必须绑定明确负面/较短期间证据，或 registry 可核验的未来披露记录。

## 2. 确定性优先的信任边界

模型输出是不受信任的数据。pipeline 会依据已检索 registry 重新绑定 citation 的 `document_id/page/published_at/source_url`，并从绑定证据推导 `claim.known_at`；模型自己生成的这些元数据不是权威。可见 FACT 文本投影为精确证据 span，DERIVED 文本投影为安全执行结果的规范形式，UNKNOWN 和 caveat 也使用确定性规范投影；executive summary 只能由已审计 claim ledger 逐句组成。模型原始摘要与 caveat 仅保留哈希，不直接进入用户可见结论。计算表达式只允许常数、变量、`+ - * / **`、括号和有限深度的一元运算，禁止函数调用、属性访问和未知变量。

处理顺序为：

1. 时间、citation identity、精确引文、数值执行、实体/期间/单位和证明图检查；
2. 计算十维原始分；
3. 应用全部硬门禁，以最严格的 cap 截断；
4. 可选地把 claim-level LLM 语义 verdict 用于 `factual_support`，但它不能撤销任何确定性失败。

## 3. 十维评分

十个权重之和为 1。每维先得到 `[0,100]` 分数 `d_j`，原始分为

\[
S_{raw}=\sum_{j=1}^{10}\alpha_j d_j.
\]

| 维度 | 权重 | 当前实现的精确定义 | 关键边界 |
| --- | ---: | --- | --- |
| `temporal_integrity` | 0.15 | 若存在 registry 中 `published_at > as_of_date` 的 evidence，或 `claim.known_at` 缺失/不等于其绑定来源中最晚发布日期，得 0；否则为 `100 × valid_fraction`。无 evidence 时为 100。 | future source 和 `known_at` 缺失/错配都会成为 temporal noncompliance 并触发 40 分门禁。 |
| `citation_correctness` | 0.14 | `100 × (identity_accuracy + exact_quote_accuracy) / 2`。identity 要求 chunk 存在，且回答展示的 document/page/published_at/source_url 均与 registry 一致；quote 必须是 chunk 文本的非空连续子串。 | 这只验证身份和逐字 span，不等于语义蕴含；规范 CitPrec 见第 5 节。 |
| `citation_completeness` | 0.09 | `100 × claim_completeness`，即 `C_v` 中至少关联一条 identity 和 exact quote 均有效 citation 的 claim 比例。 | UNKNOWN 不进入分母；当前实现不验证该 citation 是否真正支持 claim。 |
| `factual_support` | 0.10 | 有 `semantic_verdicts` 时，claim 部分按 `supported=1`、`partial=0.5`、其余或遗漏为 0；否则 FACT 逐材料 clause 必须是有效 evidence quote 的精确 span，DERIVED 必须等于规范化计算投影，INFERENCE 不获自动信用。最终再与 summary→claim 精确绑定率等权平均。 | lexical overlap 仍输出为 diagnostic，但不参与事实信用，也不能称为 entailment。claim grounding 不满 1 或 summary 出现账外材料句会触发 55 分门禁。 |
| `numeric_lineage` | 0.15 | 六项等权平均：execution accuracy、leaf binding accuracy、trace coverage、unit consistency、claim value accuracy、claim text accuracy，乘 100；另报告 claim/summary 可见数字是否具有证据或计算绑定。 | `claim_value_accuracy` 绑定 typed value 与执行值/证据值；`claim_text_accuracy` 再要求自然语言 claim 显示该 typed value（DERIVED 允许按展示精度舍入）。执行、叶值、typed value、claim/summary 可见数字任一材料错误会触发 55 分门禁；尚未做完整 XBRL tag/dimension 语义核验。 |
| `entity_period_unit` | 0.10 | 综合有效 claim–citation 的实体/期间一致性、claim–calculation 单位、source unit/currency、query entity/period 与 requested metric slots 对齐。 | 完全不回答所请求 metric slot 封顶 20，遗漏部分 slot 封顶 55；开放式问题若无可检测 slot、gold 或 semantic judge，最高 89。 |
| `proof_graph_validity` | 0.09 | `100 × max(0, 1 - I / max(1, |C| + |Calc|))`，`I` 为图错误数。 | 检查缺节点、FACT/DERIVED 无入边、DERIVED 无 calculation 边、calculation 无 evidence-bound operand 和环；任一图错误另触发 cap。 |
| `material_completeness` | 0.07 | 先算 gold key coverage（无 `K` 时仅为结构代理），再乘 answerability 结构、拒答支持、oracle 匹配、query target/metric 对齐、UNKNOWN 语言与规范投影、summary→claim 绑定。 | 无 gold 时仍不是内容完整度；无 oracle 时只能排除结构性空答和缺乏可核验证据的拒答，不能证明拒答语义正确。规范 MCR 见第 5 节。 |
| `inference_boundary` | 0.06 | INFERENCE：有证据且 `confidence < 0.95` 才通过；UNKNOWN：`confidence <= 0.5`；FACT/DERIVED：置信度落在 schema 已保证的 `[0,1]` 即通过；逐 claim 等权平均。 | 尚未验证推理本身是否合理，也未校准 confidence。 |
| `safety_and_communication` | 0.05 | “未检出投资建议”“未回显 prompt injection”“摘要非空”“caveat 等于确定性政策投影”四项等权平均。 | 当前为中英文正则和结构启发式，既可能漏检也可能误报；不是全面金融合规审查。 |

本文所称 `numeric_lineage.claim_text_accuracy` 对应 scorecard 中 `numeric_lineage` 维度的 `details.claim_text_accuracy` 字段；它由确定性 numeric audit 产生，不是 LLM judge 标签。

门禁前后的 verdict 为：`excellent`（≥90）、`strong`（≥80）、`needs_revision`（≥60）、否则 `fail`。

## 4. 硬门禁

对所有触发项收集 cap，最终分为

\[
S_{final}=\min\bigl(S_{raw},\min_{g\in G_{triggered}} cap_g\bigr).
\]

没有门禁时 `S_final = S_raw`。当前门禁是工程风险政策，**尚未经人工专家校准**。

| 门禁 | 代码触发条件 | 分数上限 |
| --- | --- | ---: |
| `future_source` | 存在截止日后的 source | 40 |
| `known_at_mismatch` | claim `known_at` 缺失或不等于最晚绑定来源发布日期 | 40 |
| `forged_or_non_exact_citation` | citation identity（含 date/URL）或 exact quote accuracy 小于 1 | 40 |
| `entity_period_unit_mismatch` | 实体、期间、source/claim/calculation 单位或币种任一材料对齐失败 | 55 |
| `unsupported_visible_claim` | 无 semantic verdict 时不是精确 evidence/canonical calculation 投影；有 verdict 时未完全支持 | 55 |
| `material_numeric_error` | execution、leaf binding、claim value/text、claim/summary 可见数字绑定任一小于 1 | 55 |
| `unsupported_investment_recommendation` | 正则检出买入、卖出、加减仓、做多做空等建议 | 60 |
| `prompt_injection_echo` | 正则检出忽略指令、要求 grader 满分等文本进入答案 | 60 |
| `noncanonical_caveat` | caveat 含确定性政策投影之外的文本 | 55 |
| `unsupported_summary_clause` | executive summary 出现不能精确绑定 claim ledger 的材料句 | 55 |
| `invalid_proof_graph` | proof graph 存在任一 validation issue | 70 |
| `invalid_answerability_structure` | answerable 无实质 claim、partial 未同时包含实质/UNKNOWN、或 unanswerable 无 UNKNOWN claim | 20 |
| `answerability_oracle_mismatch` | 输出 answerability 与预先冻结的 oracle 不一致 | 20 |
| `query_target_mismatch` | 回答未对齐查询实体或请求期间 | 20 |
| `zero_requested_metric_slots` | 一个已识别的请求指标 slot 都未回答 | 20 |
| `partial_requested_metric_slots` | 只回答部分已识别指标 slot | 55 |
| `affirmative_or_noncanonical_unknown` | UNKNOWN 含肯定事实，或不等于规范不可知投影 | 20 |
| `zero_expected_material_nuggets` | 对本应 answerable/partial 的 gold 任务，一个预期 key 都未输出 | 20 |
| `unsupported_refusal` | 无 oracle 的 partial/unanswerable 没有精确负面/较短期间证据，也没有 registry 核验的未来披露 | 55 |
| `unverified_open_ended_relevance` | 无可识别请求 slot，且没有 gold key 或 semantic verdict | 89 |

注意：`trace_coverage` 或 numeric `unit_consistency` 下降本身不会单独触发 numeric cap；但 source-unit/currency 不一致会通过实体/期间/单位门禁封顶 55。`claim_text_accuracy < 1` 会触发 55 分 cap，即使 calculation 的执行结果本身正确。缺失 FACT/DERIVED citation 通常通过 `unsupported_claim` 图错误触发 70 cap；若同时使 citation correctness 下降，则更严格的 40 cap 生效。

## 5. 跨实验的规范指标

以下名称用于论文和批量实验。凡当前代码只实现了代理指标，必须同时报告代理方法名，不得混用。

### 5.1 WCP：Weighted Claim Precision

对每个可验证 claim `c_i ∈ C_v`，令语义支持分

\[
a_i=\begin{cases}
1,& supported\\
0.5,& partial\\
0,& unsupported, contradicted, omitted.
\end{cases}
\]

则

\[
\mathrm{WCP}=\frac{\sum_iw_i a_i}{\sum_iw_i}.
\]

INFERENCE 的 `a_i` 表示“引用证据支持其明确前提且推断边界合格”，不是把预测当作已发生事实。UNKNOWN 应另评“不可知结论是否被截止日前证据充分证明”，不能简单当作正确事实。当前 `factual_support` 在有 semantic verdict 时等价于 `w_i=1` 的 claim-level WCP 代理；无 semantic verdict 时采用更保守的确定性信用规则：FACT 必须是精确证据投影、DERIVED 必须是规范计算投影、INFERENCE 得 0。该规则不是语义蕴含 WCP，lexical overlap 也不参与信用。若 `C_v` 为空，规范 WCP 记为 `N/A` 并转由 answerability/UNKNOWN 规则评估；不得把当前实现的空集默认通过冒充 claim precision。

### 5.2 MCR：Material Completeness Recall

在查看候选回答之前冻结 gold nugget 集 `K`。令 `z_k=1` 表示回答正确覆盖 nugget `k`，partial coverage 可预注册为 0.5，否则为 0：

\[
\mathrm{MCR}=\frac{\sum_{k\in K}u_k z_k}{\sum_{k\in K}u_k}.
\]

当前有 `expected_semantic_keys` 时实现的是等权、仅按 key 存在性的 MCR proxy，并与 answerability/结构/拒答支持相乘；未提供 keys 时的 `answerability_structure_no_gold_nuggets` 不是 MCR。若预注册后的 `K` 为空，规范 MCR 记为 `N/A`；对本应 answerable 的任务，空 `K` 是 gold 构建失败，不能记为 100%。

### 5.3 CitPrec 与 CitComp

对 `P` 中每个 claim–citation 对定义：identity `I_ij`、exact span `Q_ij`、claim entailment `H_ij` 均为 0/1。规范 citation precision 为

\[
\mathrm{CitPrec}=\frac{\sum_{(i,j)\in P}I_{ij}Q_{ij}H_{ij}}{|P|}.
\]

令 `V_i = {j : (i,j) ∈ P 且 I_ij Q_ij = 1}`，并令 `H_i(V_i)=1` 表示这些有效引文的**并集**完整蕴含 claim `i`。规范 citation completeness 为

\[
\mathrm{CitComp}=\frac{\sum_{i\in C_v}w_i H_i(V_i)}{\sum_{i\in C_v}w_i}.
\]

若 `|P|=0`，规范 CitPrec 记为 `N/A`；若 `C_v` 为空，规范 CitComp 记为 `N/A`。合法 UNKNOWN/拒答按单独的 answerability 规则处理。当前 `citation_correctness` 只覆盖 `I,Q`，`claim_completeness` 只要求存在 `I=Q=1` 的 citation，尚不等于上述 CitPrec/CitComp。

### 5.4 NLA：Numeric Lineage Accuracy

当前实现定义

\[
\mathrm{NLA}=\frac{EA+LBA+TC+UC+CVA+CTA}{6},
\]

其中：

- `EA`：声明结果与安全执行表达式一致的 calculation 比例；
- `LBA`：operand value 出现在绑定 evidence，或与上游 calculation 结果一致的比例；
- `TC`：operand 至少绑定有效 evidence 或有效上游 calculation 的比例；
- `UC`：operand/output 单位启发式一致程度；比率类输出和显式 `*1000` 有特殊规则；
- `CVA`：数值 claim 的 typed value 与其 calculation 结果或直接 evidence 数值一致的比例；
- `CTA`：自然语言 claim 中出现 typed value 的比例；FACT 使用规范化数值 token 精确匹配，DERIVED 按 claim 明示的小数位允许半个末位单位的舍入容差。

数值执行、typed value 与执行/证据值比较默认 `rel_tol=abs_tol=1e-6`；文本叶值查找使用规范化数值 token。只有 `CVA=CTA=1` 才能说明 typed 字段同时与执行/证据值及自然语言表述一致。NLA 必须与 entity/period/unit 维度一同解释；最终数字正确但叶节点、公司或期间错误仍是失败。当前实现中六个子项没有可评对象时均默认 1，因此必须同时报告 calculation、operand 和 numeric-claim 计数；`NLA=1, n=0` 只能解释为“未触发检查”，不能解释为数值正确率 100%。

### 5.5 PDA 与 IVR：评估器的判别力和不变性

对基础回答 `A_i` 和一个已知破坏标签的 mutation `m`，定义

\[
\mathrm{PDA}=\frac{1}{|M_d|}\sum_{m\in M_d}\mathbf 1[J(A_i)>J(m(A_i))].
\]

当前只要分数严格下降即视为检出，不要求达到某个 margin。对语义保持 mutation `t ∈ M_inv`，当前 `invariant_tolerance=1e-9`：

\[
\mathrm{IVR}=\frac{1}{|M_{inv}|}\sum_t\mathbf 1[|J(A_i)-J(t(A_i))|>10^{-9}].
\]

PDA 越高越好，IVR 越低越好。当前每题有 36 类 destructive mutations，覆盖 citation 身份/引文、未来来源与 `known_at`、query/claim 实体期间指标、source/operand/claim 单位、公式和多层可见数字、claim 极性、摘要与 caveat 侧信道、prompt injection、投资建议、空答、UNKNOWN 肯定化，以及多种不相关/跨句/已有可用证据却拒答的绕过；2 类 invariant mutations 是 claim/evidence 顺序反转和摘要空白格式变化。完整名称以 `results/synthetic_benchmark.json.coverage` 为准。因覆盖仍是预定义错误，PDA=1、IVR=0 不能外推到自然错误分布。

### 5.6 CKR、Locality 与 CausalFidelity

对一次 source mutation `m`，在 baseline proof graph 上求被改 evidence 的 claim 后代 semantic keys `D_m`。令外部形式化 oracle 提供期望映射 `O_m`，当前实现实际评估集合为 `A_m = D_m ∩ keys(O_m)`。对数值使用 `math.isclose(..., 1e-6)`；对文本先做空白/大小写规范化，再检查极性词和 token Jaccard（阈值 0.72）。

\[
\mathrm{CKR}=\frac{\sum_{k\in A_m}\mathbf 1[value_m(k)\equiv O_m(k)\land value_m(k)\not\equiv value_0(k)]}{\max(1,|A_m|)}.
\]

令 `U_m = keys(A_0) ∖ D_m`，则

\[
\mathrm{Locality}=\frac{\sum_{k\in U_m}\mathbf 1[value_m(k)\equiv value_0(k)]}{\max(1,|U_m|)}.
\]

\[
\mathrm{CausalFidelity}=\begin{cases}
\frac{2\,\mathrm{CKR}\,\mathrm{Locality}}{\mathrm{CKR}+\mathrm{Locality}},&\mathrm{CKR}+\mathrm{Locality}>0\\
0,&\text{otherwise.}
\end{cases}
\]

oracle 必须覆盖所有材料性后代；否则当前 CKR 会忽略未列入 `expected_values` 的后代。该指标验证“应变的正确变化、无关项的稳定”，比单纯存在 provenance edge 更接近因果忠实度。

## 6. Cluster bootstrap 置信区间

同一个原始问题、公司、截止日和 source snapshot 产生的所有 mutants 高度相关，必须属于同一 cluster，不能把每个 mutation 当独立样本。

### 6.1 通用单层 cluster 工具

旧的通用函数 `clustered_bootstrap_pda` 适用于只有一层独立 cluster 的 PDA 实验，算法是：

1. 输入 `cluster_id -> [bool outcome]`；
2. 以 cluster 为单位、有放回抽取与原 cluster 数相同的 keys；
3. 展开被抽中 cluster 的全部 outcomes，计算本轮 micro PDA；
4. 重复 `B=2000` 次，固定 `seed=2026`；
5. 取 bootstrap 分布的 2.5% 和 97.5% percentile 作为 95% CI。

第 `b` 次抽样可写为

\[
\hat p_b=\frac{\sum_{k\in S_b}\sum_{r=1}^{n_k}z_{kr}}{\sum_{k\in S_b}n_k}.
\]

报告必须同时给出 point estimate、cluster 数、base cases 数、每 cluster mutation 数和 CI。若不同 cluster 的 mutation 数差异明显，还应附加 cluster-macro 版本 `K⁻¹ Σ_k n_k⁻¹ Σ_r z_kr`，避免 mutation 更多的案例获得更高权重。该单层函数不是最新多公司 benchmark 的主区间算法。

### 6.2 最新多公司 benchmark 的两阶段 bootstrap

`results/synthetic_benchmark.json` 使用 `chronofin-synthetic-multicluster-v2.0`：8 家虚构公司 × 3 个财年 × 3 个问题族，共 72 个 original base tasks。每题生成 36 个破坏性和 2 个 label-preserving 变异，因此共有 2,592 个破坏性 runs、144 个保持标签 runs，合计 2,736。base answers 均来自代码可见的 synthetic formal oracle，分数均为 100 且无 hard cap。

`_hierarchical_cluster_bootstrap` 的预注册单位与步骤为：

1. 按 `company_id -> task_id -> 该题全部 38 个 mutants` 分组；
2. 第一阶段从 8 个公司 cluster 中有放回抽取 8 次；
3. 对每次抽中的公司，第二阶段从该公司 9 个 original base tasks 中有放回抽取 9 次；
4. 每次抽中原题时保留其全部 38 个相关 mutants，不在 mutant 层再次抽样；
5. 对展开样本重新计算 micro PDA、IVR、severity-drop Spearman 和各破坏子型 recall；
6. 重复 2000 次，固定 `seed=2026`，取 2.5%/97.5% percentile。

最新 point estimate 与 95% cluster-bootstrap CI 为：

| 指标 | 点估计 | 95% CI | 严格解释 |
| --- | ---: | ---: | --- |
| PDA | 1.0 | [1.0, 1.0] | 2,592/2,592 个预定义破坏性 contrast 均严格降分，36 个 subtype 的 typed-signal recall 也均为 1。 |
| IVR | 0.0 | [0.0, 0.0] | 144/144 个预定义保持标签 contrast 的分差未超过 `1e-9`。 |
| severity-drop Spearman | 0.423556 | [0.423556, 0.423556] | 预设严重度与实际降分为中等正相关；该标签不是专家校准标尺，也不应为提高相关系数而事后调级。 |

三个区间退化为点值，是因为当前确定性笛卡尔模板在 8 家虚构公司和 72 个原题上的各 mutation subtype 行为完全对称；它**不表示真实总体不确定性为零**。该 bootstrap 只刻画这 8 个虚构 company clusters 及其模板原题的抽样变化，不能覆盖 corpus 构建、自然错误分布、LLM 生成变化或人类标签不确定性。尤其不能把 `ρ=0.423556` 写成“严重度已校准”；它只能支持“在这些受控变形上存在正的单调关系，且严重度标签仍需专家校准”。

## 7. 确定性检查与 LLM 语义 judge 的边界

| 必须由确定性层裁决 | 可交给 LLM 语义 judge | LLM 不得做的事 |
| --- | --- | --- |
| source/chunk/document/page 身份；quote 是否精确子串；publication time 与 cutoff；模型元数据重新绑定；安全算术执行；operand/claim typed value；claim 文本是否显示 typed 数字；实体/期间/单位结构一致性；proof graph 缺边、缺节点和环；固定正则风险信号 | claim 与精确引文的语义蕴含、partial/contradicted；同义改写的 nugget 覆盖；材料性和反证遗漏；推断是否由已支持前提合理推出；caveat/沟通质量 | 修改 registry 事实；放行未来 source、伪引文或错误算式；用参数知识补充 source；把 lexical overlap 当作 entailment；因答案流畅、冗长或与自身风格相似而加分 |

语义-judge 接口只接收给定 claim、绑定引文、受信元数据和已验证 calculation，输出 `supported|partial|unsupported|contradicted`。候选文本和引文均按不受信任数据处理，其中的评分指令应被忽略。这里描述接口约束，不表示仓库已经为当前答案执行并封存了一次语义评判。

必须披露的当前限制：

- 没有 `semantic_verdicts` 时，`factual_support` 只给 exact evidence span 与 canonical executed-calculation projection 信用；`lexical_overlap_diagnostic` 仍可观察，但不参与得分；
- 仓库保留的 `results/public_tencent_semantic_stability_final.json` 是**历史 Hy3 judge 重复记录**，其 `evaluation_scope=historical_answer_projection`，历史答案字节没有独立封存，且它不绑定当前 projection/当前腾讯答案字节；不能称为“当前语义稳定性”；
- 该历史记录中 3 次 × 5 claims 为 15/15 `supported`，语义增强分 100/100/100；更早 `*_v1_before_table_context.json` 的 exact agreement rate=0.2、supported rate=0.6、分数 96/96/100。两者输入上下文与 prompt 不同，只能保留为协议敏感性的历史失败—修订记录；
- 当前可绑定的稳定性证据是 `results/public_tencent_current_deterministic_stability.json`：披露前/后两个当前答案各确定性重算 5 次，分数均 100、scorecard 字节摘要各自完全一致、无模型调用且不声称语义蕴含；
- 因此语义 judge 应作为可审计的软判定，不能作为硬事实 authority。上线前应采用跨家族 judge、顺序/提示改写复测、置信度校准和 abstention/升级机制。

## 8. 当前结果可以和不可以证明什么

| 结果文件 | 已观察结果 | 合法结论 | 不得外推 |
| --- | --- | --- | --- |
| `results/offline_experiment.json` | CC0 合成数据：good/medium/bad 为 100/55/40；36 个 destructive mutations 的 PDA=1；2 个 invariant mutations 的 IVR=0；severity-drop Spearman≈0.424；单个 causal fixture 三项指标均为 1；确定性层 20 次完全一致 | 当前实现能识别这些手工构造错误，并覆盖可见摘要/caveat、查询对齐、UNKNOWN 和拒答侧信道 | 真实错误检出率、人类一致性、生产投资准确率；严重度标签未由专家校准 |
| 同文件 PIT ablation | strict retrieval future leak=0，naive retrieval=3 | 时间硬过滤在该合成案例有效 | 对所有网页/修订披露均无泄漏 |
| `results/synthetic_benchmark.json` | 8 家虚构公司、72 个 formal-oracle 原题、每题 36 个破坏性和 2 个保持标签变异，共 2,736 runs；PDA=1（95% CI [1,1]）、36 类 recall 均为 1、IVR=0（[0,0]）、severity-drop Spearman=0.423556（退化 CI 同点值） | 当前确定性 evaluator 在该完整可见模板矩阵上检出全部预定义破坏，并对两类预定义等价变换不改分 | held-out 金融问答能力、真实错误分布、人类一致性；相关系数仍来自模板化严重度，不等于专家校准 |
| `results/evaluator_ablation.json` | 同一 2,736-run 矩阵上的 4 种审计策略，共 10,944 outcomes：plain 0%、exact citation 5.56%、PIT+citation 13.89%、full 100%，四者 IVR=0 | 在相同受控变异上，精确引用、时间检查与完整图/数值/拒答/可见投影门禁带来单调、可定位增益 | 不是等预算 Hy3/RAG 端到端答案质量基线，也不是外部模型比较 |
| 历史 v1 三公司记录：`results/postfreeze_challenge_v1*.json` | 四个数据文件保持同一哈希；仓库内历史结果保留 3/6→6/6，3/3 future-leak 负例被拒 | 可复核历史结果与最终结果内嵌 evaluator manifest 的内部一致性 | 无外部可信时间戳；首个失败运行完整 evaluator 身份不可证；当前树不是历史冻结树 |
| 当前 v2 三公司回归：`results/postfreeze_challenge_v1_current_regression*.json` | 相同已见数据上 0/6→6/6，最终有效案例均为 100，3/3 负例均为 20；当前 evaluator、adapter、前后结果独立入账 | 当前加固评估器与适配器没有丢失这组已知真实格式案例，且失败—修复链可审计 | 明确是 seen regression，不是 post-freeze、held-out、人工评测或 Hy3 生成准确率 |
| `results/cleanroom_verification.json` | 移除 API/代理环境、禁网、临时 checkout/新 venv 中测试、实验、回归、CLI、Git staging 与 submission verifier 均通过，缓存 PDF 为 0 | 已提交核心离线链路不依赖秘密变量或本机财报缓存 | venv 继承当前主机 build tooling；不是第三方机器复现，也不覆盖在线 Hy3 调用 |
| `results/live_causal_experiment_current.json` | 当前确定性层重绑定两份历史 Hy3 保存答案；净利润 144→180 时 CKR=Locality=CausalFidelity=1，前后 score 均 100 | 输入哈希绑定的当前因果重处理在该单例上响应正确且局部 | 本次无模型调用；不能把历史生成冒充当前 Hy3 在线结果或统计显著的因果可靠性 |
| `results/live_stability.json` | 历史 3 次 Hy3：分数均 100，数值 range=0，semantic-key pairwise Jaccard≈0.889 | 保留历史运行在该固定样例上的重复性 | 未重新绑定当前 projection/evaluator；不是当前生成稳定性、human-human agreement 或正确性证明 |
| `results/public_tencent_semantic_stability_final.json` | 历史 Hy3 judge 记录：3×5 为 supported、分数 100/100/100；旧版本为 0.2/0.6 和 96/96/100 | 只能说明保留的历史 prompt/trace 记录中的重复结果及协议修订链 | 未绑定当前答案 projection，历史答案字节也未独立封存；不是当前语义稳定性、人类一致性或跨样例可靠性 |
| `results/public_tencent_current_deterministic_stability.json` | 当前披露前/后答案各确定性重算 5 次，全部 100、各自 scorecard hash 完全一致、population std=0 | 当前答案字节与当前确定性 evaluator 的实现重复一致 | 无模型调用且不执行语义蕴含判断；不能替代生成稳定性或专家一致性 |
| `results/public_tencent_*_final_score.json` | 截止日前拒答和披露后回答的确定性 final score 均为 100 | 身份、时间、引文 span、算术和图等当前启用检查未报错 | factuality 或 material completeness；两份 scorecard 都明确无 semantic entailment judge、无 gold nuggets |

不同文件来自不同修订轮次。例如 `public_tencent_summary.json` 与 `public_tencent_after_publication_final_score.json` 属于不同重处理阶段；语义稳定性的 v1、intermediate 与 final 也使用不同证据上下文/prompt hash。历史 Hy3 结果、当前确定性重处理、历史 v1 challenge 和当前 v2 seen regression 必须分别命名，报告时绑定确切文件、输入哈希、模型配置和代码版本，不能混合版本取最好结果。

该历史阶段未新增专家标注。后续已执行的FinanceBench公开人工标签三分类验证见[外部人工标签验证](外部人工标签验证.md)；十维开放式评分仍无新增专家盲标。

## 9. 最小报告要求

任何对外结果至少同时报告：

- 十维原始分、`raw_score`、所有 hard gate、`hard_cap` 和 `final_score`；
- factual 方法是 semantic judge 还是 exact-evidence/canonical-calculation deterministic projection；若报告 lexical overlap，必须明确它仅为 diagnostic、不参与事实信用；
- 是否提供冻结的 gold nuggets，MCR 是规范值还是 structural proxy；
- WCP、MCR、CitPrec、CitComp 的分子、分母和 UNKNOWN 处理；NLA 六个子项及 calculation、operand、numeric-claim 计数；
- mutation 列表、base cluster 数、公司数、PDA/IVR/严重度相关及 bootstrap 层级、CI；
- causal oracle 来源、被改叶节点、完整后代集合、CKR/Locality/CausalFidelity；
- 模型、prompt/version/hash、temperature/reasoning effort、运行时间和失败重试；
- “未执行人工标注”或真实的人类协议版本，不得用重复稳定性替代专家一致性。
