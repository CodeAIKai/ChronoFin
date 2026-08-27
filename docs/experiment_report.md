# ChronoFin 实验报告

版本：2026-08-27  
目标：验证 ChronoFin 是否真的执行时间隔离、证据/计算审计与因果局部响应，而不是只生成一篇看起来专业的报告。

## 1. 实验问题

本轮实验预先区分五类问题：

1. **判别力**：已知正确输出被最小破坏后，评估器是否稳定降分？
2. **不变性**：只改变顺序和空白时，评估器是否错误降分？
3. **时点性**：未来财报是否在调用 Hy3 前就被隔离？
4. **因果忠实性**：改变一个证据叶时，图后代是否正确变化、非后代是否稳定？
5. **模型稳定性**：Hy3 重复生成/复评时，关键数值、答案可答性和语义结论是否一致？

确定性结果与 Hy3 结果分开报告；合成数据与真实 PDF 分开报告；没有执行的人类标注不会被写成实验结果。

## 2. 环境与可复现入口

- Python：3.12（核心代码要求 >=3.10）
- Hy3 endpoint：`https://tokenhub.tencentmaas.com/v1`
- 模型：`hy3`
- 生成温度：0
- prompt 版本：生成结果 provenance 中的 `prompt_version` 与 `prompt_hash`
- 合成语料：`data/demo/`
- 真实语料：腾讯官方 2024 年报、2025 半年报、2025 年报；URL 与哈希见[数据卡](data_card.md)
- 三公司格式挑战：Apple SEC XBRL、Microsoft 官方 IR HTML/XBRL、NVIDIA 官方 IR PDF 的短摘录；历史 v1 有相对当时 evaluator 的冻结记录，当前 evaluator 只把同一数据作为已见回归；来源、哈希和边界同见数据卡

离线复现：

```bash
PYTHONPATH=src python -m unittest discover -s tests -t . -v
PYTHONPATH=src python scripts/run_offline_experiments.py
PYTHONPATH=src python scripts/run_synthetic_benchmark.py
PYTHONPATH=src python scripts/run_evaluator_ablation.py
PYTHONPATH=src python scripts/run_postfreeze_challenge.py --verify-only
PYTHONPATH=src python scripts/run_postfreeze_challenge.py
PYTHONPATH=src python scripts/reprocess_saved_causal.py
PYTHONPATH=src python scripts/verify_submission.py
```

真实 PDF 实验：

```bash
python scripts/download_public_reports.py
PYTHONPATH=src python scripts/run_public_tencent_demo.py

PYTHONPATH=src python scripts/reprocess_saved_answer.py \
  --manifest data/cache/tencent/manifest.json \
  --answer results/public_tencent_before_publication.json \
  --output-prefix results/reproduced_tencent_before \
  --expected-answerability unanswerable

PYTHONPATH=src python scripts/reprocess_saved_answer.py \
  --manifest data/cache/tencent/manifest.json \
  --answer results/public_tencent_after_publication.json \
  --output-prefix results/reproduced_tencent_after \
  --expected-answerability answerable

PYTHONPATH=src python scripts/run_deterministic_stability.py --runs 5
```

`run_public_tencent_demo.py` 需要在环境变量中提供 TokenHub Hy3 密钥；两个重处理命令与确定性稳定性命令不调用模型。所有结果保留原始 JSON；HTML 只是展示层。

## 3. 离线形式化实验

### 3.1 好/中/差输出

同一个 CC0 合成财报金夹具构造三档：

| 档位 | 操作 | 最终分 | 硬上限 |
| --- | --- | ---: | ---: |
| Good | 完整证据、计算和图 | 100 | 无 |
| Medium | 删除一个材料结论的引用 | 55 | 55 |
| Bad | 伪造精确引文 | 40 | 40 |

结果满足 good > medium > bad，但这只是可控夹具上的评估器单元测试，不是自然分布准确率。

### 3.2 Contrast / invariant suite

当前 registry 有 36 类 label-changing 变形，按风险面分为：

- 来源与时点：伪引文、引用元数据伪造、未来泄漏、`known_at` 错配/缺失；
- 目标与语义：实体、期间、claim 文本实体/期间、极性、query 实体/期间/指标错配；
- 数值与单位：claim/fact/operand 单位、公式、claim 文本数值、额外数字、中文数字和摘要数字错误；
- 摘要、引用与安全：不受支持摘要、缺引文、正文/caveat 提示注入、caveat/祈使式投资建议、虚假 caveat 断言；
- 可答性与拒答：空答案、肯定式 UNKNOWN、一律拒答、结构化错误拒答，以及不相关未来/负面证据、跨分句负面证据和已有可答材料时仍以未来披露拒答。

2 类 label-preserving 变形仍为 claim/evidence 顺序反转和空白格式变化。

| 指标 | 结果 |
| --- | ---: |
| Paired Discrimination Accuracy (PDA) | 1.000 |
| Invariance Violation Rate (IVR，越低越好) | 0.000 |
| 错误严重度—分数下降 Spearman | 0.423556 |

36 类变形的 score drop 与 typed signal 均被检出；逐变形分数和硬门禁见 [offline_experiment.json](../results/offline_experiment.json)。`ρ=0.423556` 是项目自定严重度标签与离散硬门禁降分的正相关，不是专家校准量表，不能为追求更高相关系数而事后改标签。变形模板与规则由同一项目设计，因此结果主要证明实现自洽，不能替代独立 benchmark 或专家效度。

### 3.3 时间过滤消融

问题为“截至 2025-12-31，FY2025 全年净利润是多少”。语料中故意放入 2026-03-20 才发布的 FY2025 年报：

| 检索配置 | 截止日后 chunk 数 |
| --- | ---: |
| 严格 `published_at <= cutoff` | 0 |
| 关闭时间过滤的 naive baseline | 3 |

严格模式还将未来年报写入隔离日志。这证明过滤发生在 prompt 构造之前；它不能证明 manifest 的发布日期本身永远正确。

### 3.4 形式化因果 oracle

把 FY2024 净利润证据从 144 变为 180，收入保持 1,200。证明图 oracle 预期净利润和净利率是后代，收入、驱动和风险是非后代：

- 观察到净利润更新为 180；
- 派生净利率从 12% 更新为 15%；
- 无关 semantic key 保持等价；
- CKR = 1，Locality = 1，Causal Fidelity = 1。

确定性评分重复 20 次均为 100，range = 0；该结果只说明确定性层无采样随机性，不等于人工一致性。

### 3.5 空答案 / 一律拒答对抗审计

独立投稿审计发现旧 evaluator 的空集合默认值可被利用：`answerable`/`partial` 空答案可得 93，`unanswerable` 只写一句摘要可得 100；即使传入 gold keys，空答仍可能保持 93。这一失败直接否定了旧版“评估器不可博弈”的主张。

当前版本同时检查 answerability 与 claim 结构、预注册 answerability oracle、拒答证据的目标/期间/指标槽位和分句绑定、已有可答材料、未来隔离以及 gold key 零覆盖。`empty_answer`、`affirmative_unknown_claim`、`blanket_refusal`、`incorrect_refusal`、`irrelevant_future_refusal`、`unrelated_negative_refusal`、`cross_clause_negative_refusal`、`available_source_future_refusal` 均进入正式矩阵；合法 UNKNOWN 则必须使用确定性认识边界投影并满足可核验证据/注册表条件。

### 3.6 72 题多簇形式化压力集

为降低“评估器只会通过一个手工夹具”的风险，固定矩阵包含 8 个虚构公司 × 3 个财年 × 3 个问题族（盈利能力/净利率、收入同比、流动比率），共 72 个 base task。每题运行 36 类破坏性和 2 类 label-preserving 变异，共 2736 次：2592 次破坏、144 次等价。

| 指标 | 点估计 | 两阶段 cluster bootstrap 95% CI |
| --- | ---: | ---: |
| PDA | 1.000 | [1.000, 1.000] |
| IVR | 0.000 | [0.000, 0.000] |
| 严重度—降分 Spearman | 0.423556 | [0.423556, 0.423556] |

36 类破坏性变形的 typed recall 均为 1.0。bootstrap 固定 seed=2026，先重采样公司，再重采样公司内原始题，并保留每题全部 38 个相关变异；没有把 2736 个 mutant 当成独立样本。

结果见 [synthetic_benchmark.json](../results/synthetic_benchmark.json)。区间退化并不意味着真实世界零不确定性，而是所有可见模板在所有虚构簇上得到相同形式化结果；它不覆盖模板构造偏差、真实 PDF 噪声或人工标签不确定性。`ρ=0.423556` 也只是当前模板严重度关系，不能解释为专家严重度标尺已经校准。

## 4. Hy3 合成语料实验

### 4.1 历史 Hy3 时点问答记录

三个端到端案例曾由 Hy3 生成后经当时的确定性层回绑和评分：

| 案例 | 预期 | 最终分 |
| --- | --- | ---: |
| FY2024 已披露分析 | 可答，含收入/利润/净利率/驱动/风险 | 100 |
| FY2025 年报披露前 | 不可答，不把半年报年化为全年 | 100 |
| FY2025 年报披露后 | 可答并给完整血缘 | 100 |

结果见 [live_demo_summary.json](../results/live_demo_summary.json)。它们用于保留开发历史，不等同于当前投影下重新调用 Hy3；当前报告只把已明确重处理并重新评分的结果称为“当前”。

### 4.2 端到端 causal mutation

第一次运行虽然 CKR=1，但 Locality=0.667、Causal Fidelity=0.8。失败原因不是数值错误，而是 Hy3 在两次答案中对相同含义使用了不稳定 semantic key / 措辞，导致非后代比较误判。原始失败保留在 [live_causal_experiment_v1_before_fix.json](../results/live_causal_experiment_v1_before_fix.json)。

修复包括：

- 对常见财务指标和客户集中度建立小型 canonical ontology；
- 语义键比较加入保守的、否定词感知的等价判断；
- 不用宽松字符串相似覆盖数值或极性变化。

历史复跑曾达到三个指标均为 1。随后用 `scripts/reprocess_saved_causal.py` 将两份已保存 Hy3 答案重新绑定到当前确定性投影；该过程不联网、不调用模型。当前 [live_causal_experiment_current.json](../results/live_causal_experiment_current.json) 中 CKR、Locality、Causal Fidelity 均为 1，baseline/mutated 当前分数均为 100。它证明这一保存响应/单叶合成干预在当前规则下保持正确响应与局部性，仍不能估计总体成功率，也不是一次新的 Hy3 生成实验。

### 4.3 历史三次生成稳定性

同一 FY2024 问题调用 Hy3 三次：

- answerability 三次完全一致；
- 确定性评分为 100/100/100，population std = 0；
- 收入 1,200、净利润 144、净利率 12 的 range 均为 0；
- future leak runs = 0；
- semantic-key 两两 Jaccard 均值 = 0.889；
- 一次调用因首个输出 JSON 不完整而在第二次 attempt 成功。

原始 trace（latency、usage、attempts、prompt hash）见 [live_stability.json](../results/live_stability.json)。这是旧输出契约下的历史 Hy3 记录，未重新绑定当前投影；三次重复样本也很小，不可称为当前稳定性、生产 SLA 或人类一致性。

## 5. 真实腾讯官方 PDF 实验

### 5.1 问题与时间线

同一问题询问 Tencent Holdings Limited FY2025 全年收入、归母利润和派生利润率：

- 截止 `2025-12-31`：2025 半年报已公开，FY2025 年报尚未发布；
- 截止 `2026-04-10`：发布日期为 2026-04-09 的 FY2025 年报已经可用。

### 5.2 最终结果

披露前保存响应经当前确定性投影重处理后为 `unanswerable`，明确说明半年数据不能作为全年值；当前确定性分数 100。

披露后答案给出：

- FY2025 revenues = RMB 751,766 million；
- IFRS profit attributable to equity holders = RMB 224.8 billion，经显式 `*1000` 转为 RMB 224,800 million；
- non-IFRS profit attributable to equity holders = RMB 259,626 million；
- IFRS profit margin = 29.9029%；
- non-IFRS profit margin = 34.5355%。

收入与 non-IFRS 利润引用包含“Year ended 31 December、2025/2024、RMB in millions”表头；IFRS 利润引用包含完整指标名、数值和期间。两个利润率均由安全执行器复算。披露后当前确定性分数 100。

证据：

- [披露前答案](../results/public_tencent_before_publication_final.json)与[评分](../results/public_tencent_before_publication_final_score.json)
- [披露后答案](../results/public_tencent_after_publication_final.json)与[评分](../results/public_tencent_after_publication_final_score.json)

### 5.3 真实案例失败—修复链

以下 1–5 是历史 Hy3 生成/语义复评链，保留它们是为了展示失败，但第 5 步的三次语义复评绑定的是旧版答案字节，不能当作当前投影的语义证明。第 6 步及 5.4 节描述当前确定性边界。

本项目保留失败而不是只展示最终高分：

1. **输出预算不足**：初始 `max_tokens=6000`，Hy3 连续产生截断/不完整 JSON，4 次尝试后失败；见 [public_tencent_failure_v1.json](../results/public_tencent_failure_v1.json)。修复为 10k 输出预算、较少 top-k 和带原因的重试。
2. **数值与图血缘错误**：第二版在披露前/后均为 55；原因包括对不需要的上一期间做换算、模型结果和执行值不一致、计算到计算的依赖未显式表示；摘要见 [public_tencent_summary_v2_before_fix.json](../results/public_tencent_summary_v2_before_fix.json)。修复为信任执行器结果并推断严格的上游 calculation edge。
3. **裸表格数字**：确定性分数可达 100，但语义 judge 因数字行缺少期间表头，最初逐 claim 完全一致率仅 0.2、supported rate 0.6，分数 96/96/100；原始结果见 [public_tencent_semantic_stability_v1_before_table_context.json](../results/public_tencent_semantic_stability_v1_before_table_context.json)。
4. **表头补全后的残余歧义**：加入表头继承后，supported rate 提升为 0.867，但 `RMB224.8 billion ... 2025` 的引文仍缺“Profit attributable to equity holders”指标名，三次中一次将相关两条 claim 判为 partial。
5. **历史语义修复**：精确引文若从句中部开始，即使长度较长且含年份，也扩展到完整连续原文行；来源仍必须是检索到的精确子串。当时 5 条 claim × 3 次复评全部为 supported，增强分数 100/100/100、population std = 0，见 [public_tencent_semantic_stability_final.json](../results/public_tencent_semantic_stability_final.json)。该结果未绑定当前投影后的答案 SHA-256。
6. **typed value 正确但文案错误**：最新 Hy3 重跑中，执行器得到 IFRS/non-IFRS 利润率 29.9029%/34.5355%，但原始 claim 文本写成 29.9073%/34.5584%。旧评估器只核对 JSON value，曾错误放行。新增 `claim_text_accuracy` 后，此类冲突封顶 55；管线只在公式结果位置无歧义时按相同小数位同步文本，并在 provenance 保存原文和修正版。最终三者（文案、typed value、执行器）一致。

这条失败链说明表格引用不能只截数字：实体、期间、单位和指标名必须同时进入证据窗口。也说明 LLM judge 适合暴露语义歧义，但不能推翻确定性的时间、身份和算术事实。

### 5.4 当前确定性稳定性

`PYTHONPATH=src python scripts/run_deterministic_stability.py --runs 5` 对当前披露前/后答案各重复评分 5 次，不联网、不调用模型。两组分数均为 5 个 100，组内评分卡 SHA-256 完全一致，见 [public_tencent_current_deterministic_stability.json](../results/public_tencent_current_deterministic_stability.json)。这是实现确定性的证据，不是模型语义复评；历史 Hy3 三次复评不能填补这一差别。

## 6. 组件消融与三公司版本化回归

### 6.1 四策略审计组件消融

在同一 72 题 ×（36 破坏 + 2 等价）上，比较 no-audit/plain-output、exact-citation-only、point-in-time + exact-citation 和 full ChronoFin。每策略 2736 条、四策略共 10944 条 outcome；破坏检出率依次为 0、0.055556、0.138889、1，四者 IVR 均为 0。完整逐类结果见 [evaluator_ablation.json](../results/evaluator_ablation.json)与[方法说明](evaluator_ablation.md)。这是 evaluator 能力消融，不是 Hy3/RAG 端到端答案准确率或外部模型强基线。

### 6.2 三公司挑战：历史 v1 与当前已见回归

历史 v1 中，evaluator 冻结后才由 AI 策展者从 Apple SEC XBRL、Microsoft 官方 IR HTML/XBRL、NVIDIA 官方 CFO Commentary PDF 构建 3 家公司、3 种披露表示、6 个前后时点 gold 和 3 个 future-leak 负例；数据与当时 evaluator 分别以 SHA-256 记账。历史首轮保留为 3/6；只修当时适配器后为 6/6，3/3 未来泄漏负例均为 20。见[历史首轮](../results/postfreeze_challenge_v1.json)与[历史修复后](../results/postfreeze_challenge_v1_after_adapter_fix.json)。这段“post-freeze”只相对历史 v1 成立。

当前 evaluator 的安全加固发生在这些数据已经可见之后，因此当前运行明确标为 `known_data_regression_current_evaluator_v2`，不能称 post-freeze、held-out 或盲测。当前首轮因指标槽位别名不能识别这些官方指标而为 0/6，失败固定在 [postfreeze_challenge_v1_current_regression.json](../results/postfreeze_challenge_v1_current_regression.json)；只修当前适配/槽位映射、未改题目/日期/数字/引文/URL 后为 6/6，3/3 future-leak 负例仍为 20，见 [postfreeze_challenge_v1_current_regression_after_slot_fix.json](../results/postfreeze_challenge_v1_current_regression_after_slot_fix.json)。

这组数据只支持两个有限结论：历史 v1 的冻结后失败—修复链可核验；当前 evaluator 对已知三格式的回归不退化。它不支持当前 evaluator 的陌生格式泛化、人工专家一致性、统计 held-out 或端到端 Hy3 正确率。

### 6.3 无网无密钥干净环境复现

`scripts/run_cleanroom_check.py` 会计算提交树指纹，将项目复制到随机临时目录，移除 Hy3/OpenAI 密钥与代理环境变量，设置 `PIP_NO_INDEX=1`，再在新虚拟环境执行离线核心链路。由于当前提交树仍在收尾，本报告不预写步骤数或通过结论；最终状态只以收尾后重新生成、树指纹匹配且由 `verify_submission.py` 校验的 [cleanroom_verification.json](../results/cleanroom_verification.json) 为准。

即使最终通过，它也只能排除“依赖未提交 PDF 缓存、API Key 或当前工作目录状态”的一类复现风险；它仍继承宿主 build tooling，不是第三方系统复现，也不重放在线 Hy3 调用。

### 6.4 提交演示资产

`scripts/build_demo_gif.py` 从冻结的腾讯前后时点答案、因果实验、正式 benchmark 与组件消融 JSON 生成 1280×720、56 秒的离线 GIF，不联网、不调用模型、不读取密钥。资产见 [chronofin_demo.gif](../assets/chronofin_demo.gif)，带口播版本见[两分钟脚本](demo_script.md)。GIF 展示的是已落盘证据的回放，不冒充可交互在线运行。

## 7. 当前结论与不成立的主张

### 本轮已经支持

- 检索前时间硬过滤能阻断构造案例和真实腾讯案例中的未来年报；
- 来源元数据回绑、精确引文、受限算式和证明图可端到端运行；
- 72 个形式化 base task 上，36 类受控错误均能降分且触发预期 typed signal，两类格式不变变换均不降分；
- 四策略消融在相同攻击矩阵上显示完整审计层相对简化组件的增量覆盖；
- 历史 v1 三公司挑战保留 3/6→6/6 的冻结后记录；当前已见回归保留 0/6→6/6，且 3/3 future-leak 负例被拒绝；
- 保存的 Hy3 因果答案在当前确定性投影下重处理后，单个证据叶干预的 CKR、Locality、Fidelity 均为 1，前后评分均为 100；
- 真实腾讯披露前/后答案当前确定性评分均为 100，各重复 5 次的评分卡完全一致。

### 本轮没有支持

- 没有证明跨公司、跨行业、跨 PDF 版式的总体准确率；三公司挑战仍小、偏科技且非人工；
- 没有双专家标注或 human–human / human–evaluator agreement；
- 没有证明 manifest 日期在修订、重述、时区和盘中情形下始终正确；
- 没有证明同族 Hy3 judge 无自偏好；
- 历史三次 Hy3 语义复评未绑定当前投影后的答案，因而没有证明当前答案的三次语义一致性；
- cleanroom 只有在最终提交树稳定后重跑并通过指纹核验，才能写入最终通过结论；
- 没有把合成 PDA=1、单次 causal fidelity=1 或内部 100 分解释为真实投资可靠性；
- 没有提供任何买卖建议、回报预测或生产部署承诺。

人工校准的预注册步骤见[人工标注协议](human_annotation_protocol.md)。在实际招募、盲标和仲裁完成之前，结果表必须继续标记为“未执行”。

## 8. 下一轮优先级

1. 新建由开发者未见、专家独立构造和仲裁的真实公司 held-out 集；当前三公司数据已被开发者看见，只保留为版本化回归；
2. 在相同证据和调用预算下加入 plain Hy3、普通 RAG、exact-citation RAG 的端到端生成基线；当前仅完成 evaluator 组件消融；
3. 使用至少两名具备财报阅读能力的独立标注者校准引用蕴含、重要信息覆盖和推断边界；
4. 建模 amendment/supersedes、首次可得时间、修订生效时间与跨时区；
5. 引入结构化表格/XBRL 或页面视觉通道，但继续以官方原文作为最终可读证据。
