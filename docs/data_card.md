# ChronoFin 数据卡

> 适用版本：历史规则评估器及其确定性回归。当前开放式研究应用见[实验分析报告](最终实验分析报告.md)与[十维评估方法](开放式评估方法.md)。下文的“当前”指该历史阶段。

版本：v1.2（2026-08-27）  
适用范围：`data/demo/` 合成演示集、`data/public/tencent_sources.json` 指向的腾讯公开财报，以及 `data/challenge/` 中带哈希账本的三家公司官方披露短摘录。

## 1. 数据用途与时间语义

本项目用三类数据验证“时点可知、证据可追、计算可执行、变更可归因”的财务问答。每份文档都有文档级 `published_at`；查询只允许使用 `published_at <= as_of_date` 的材料。日期精度为自然日，不表达盘中发布时间、时区差异或交易所接收时间。

预期用途包括时点问答、未来信息泄漏测试、引用与数值血缘审计、证明图构建及受控因果变形。它不是投资建议数据集，也不应用于训练或证明真实市场中的收益、准确率或泛化能力。

## 2. 合成演示数据

清单：`data/demo/manifest.json`  
许可：清单声明为 [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/)  
内容：项目构造的中文 Markdown 财报；公司名称“云舟科技”及全部数字均为虚构，不对应真实主体，不含个人数据。

| 文档 ID | 内容 | 报告期 | `published_at` | 设计作用 |
| --- | --- | --- | --- | --- |
| `cloud_2024` | 云舟科技 2024 年年度报告（合成） | FY2024 | 2025-03-18 | 事实、风险、驱动与净利率计算血缘 |
| `cloud_2025_h1` | 云舟科技 2025 年半年度报告（合成） | H1 2025 | 2025-08-25 | 验证半年数据不能被年化成全年答案 |
| `cloud_2025_annual` | 云舟科技 2025 年年度报告（合成） | FY2025 | 2026-03-20 | 截止日前的“未来诱饵”及截止日后的答案解锁 |

合成集刻意小而可控，适合确定性单元测试和反事实实验：例如把 FY2024 净利润从 144 改为 180 百万元，预期只有净利润及其派生净利率从 12% 变为 15%，收入、驱动和风险应保持不变。该集只有一个虚构主体、三份短文档且算式简单，不能代表真实 PDF 的版式噪声、会计口径歧义、跨公司分布或专家标注质量；`results/offline_experiment.json` 也明确不声称存在人工金标。

## 3. 腾讯官方 PDF 快照

入口：[腾讯投资者关系—财务报告](https://www.tencent.com/investors/financial-reports/)  
源清单：`data/public/tencent_sources.json`  
本地缓存清单：`data/cache/tencent/manifest.json`

以下发布日期来自项目源清单，URL 均指向 `static.www.tencent.com`；SHA-256 与字节数对应 2026-08-26 复核的本地二进制快照。

| 文档 ID | 报告 / 报告期 | 发布日期 | 腾讯官方 PDF | SHA-256 | 字节数 |
| --- | --- | --- | --- | --- | ---: |
| `tencent_2024_annual` | Annual Report 2024 / FY2024 | 2025-04-08 | [PDF](https://static.www.tencent.com/uploads/2025/04/08/1132b72b565389d1b913aea60a648d73.pdf) | `95b0652da8294527d150a56a9de293627b53e73b4a4c21202c153ea6eb4e9134` | 4,754,924 |
| `tencent_2025_interim` | Interim Report 2025 / H1 2025 | 2025-08-26 | [PDF](https://static.www.tencent.com/uploads/2025/08/26/d1d2fb988f5e910e254b3abb41dadb0f.pdf) | `c9e013790537e998e78d6c4850b74f3f8eb9831c9a9bc5c552333bbda19cc3ee` | 7,267,254 |
| `tencent_2025_annual` | Annual Report 2025 / FY2025 | 2026-04-09 | [PDF](https://static.www.tencent.com/uploads/2026/04/09/62d786fcf3d3c8cb7e54791ee95439ac.pdf) | `2a7547168077c3d9994af673125e77612e8656bc0f17ad189371d7e4088f4e98` | 3,999,857 |

`scripts/download_public_reports.py` 从上述官方 URL 下载文件，检查响应为 PDF、文件至少 100 KB，并将实际 SHA-256 和大小与源清单的固定值比较；任一哈希或字节数不符即 fail closed，不会静默接受替换文件。匹配后才写入缓存清单，摄取器加载时会再次校验文件哈希；PDF 由 PyMuPDF 抽取，未安装时回退到 `pdftotext -layout`，同时保留页码、文档 ID、发布日期和源 URL。上游若替换同一 URL 下的文件，应停止复现实验、核对是否为更正版，并为新快照单独版本化。

## 4. 三公司短摘录挑战：历史记录与当前回归

清单：`data/challenge/challenge_v1.json`  
数据账本：`data/challenge/FROZEN.sha256`（清单 + 三个摘录，共四个文件）  
历史记录账本：`data/challenge/HISTORICAL_V1_RESULTS.sha256` 与 `data/challenge/EVALUATOR_FROZEN.sha256`  
当前回归账本：`data/challenge/EVALUATOR_CURRENT_V2.sha256`、`data/challenge/ADAPTER_CURRENT_V2.sha256` 与 `data/challenge/CURRENT_V2_REGRESSION_CHAIN.sha256`  
策展方式：AI 根据官方公开披露构造；无人类金融专家标注或仲裁。

`challenge_v1.json` 与三个本地摘录在两条修复链中保持同一组四文件哈希，用于检查陌生官方披露表示的时点、精确引文、数值血缘和拒答结构。仓库保留的历史 v1 记录为 3/6→6/6；但它没有外部可信时间戳，首个失败运行的完整 evaluator 身份无法验证，且历史 runner 源码不再能按记录哈希复原。因此不能把当前代码树称为历史冻结树，也不能把这个仓库内记录描述成独立证明的 held-out 实验。

当前 evaluator 经红队加固后已不同于 v1。相同四个数据文件上的当前结果明确标为 **seen-data regression**：首轮 0/6 暴露通用 metric-slot alias 缺口，修复通用 alias 后为 6/6；两轮均拒绝 3/3 future-leak 负例，且数据问题、日期、数值、引文和 gold 均未修改。当前 evaluator、materialization adapter、前后结果和修复清单分别入账；完整证据边界见[挑战报告](postfreeze_challenge_report.md)。

| 主体 / 期间 | 官方表示与发布日期 | 本地保存内容 | 冻结时点对 |
| --- | --- | --- | --- |
| Apple Inc. FY2024 | [SEC EDGAR XBRL presentation HTML](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/R3.htm)，2024-11-01 | Net sales、Net income 两条短表格行 | 2024-10-30 拒答；2024-11-02 可答 |
| Microsoft FY2025 | [投资者关系 Income Statements HTML/XBRL](https://www.microsoft.com/en-us/Investor/earnings/fy-2025-Q4/income-statements)，2025-07-30 | Total revenue、Net income 两条短表格行 | 2025-07-29 拒答；2025-07-31 可答 |
| NVIDIA FY2025 | [官方 CFO Commentary PDF](https://investor.nvidia.com/files/doc_financials/2025/Q425/Q4FY25-CFO-Commentary.pdf)，2025-02-26 | Revenue、Net income 两条短表格行 | 2025-02-25 拒答；2025-02-27 可答 |

本地 Markdown 是 AI 转录的精确短摘录，不是完整报告副本；哈希只能证明本地摘录未改变，不能证明上游网页持续可用或字节身份不变。6 个有效答案是 declarative gold 的确定性 materialization，3 个负例把披露后答案移到披露前截止日。因此历史链只是一条有明确缺口的仓库内记录，当前链只验证已见数据上的 evaluator/adapter 回归；二者都不是三家公司上的新鲜 Hy3 问答准确率、人工评测或统计 held-out 泛化。

## 5. 许可与分发边界

- 仓库根 `LICENSE` 的 Apache-2.0 只覆盖 ChronoFin 自有代码与文档，不会把第三方财报重新许可为 Apache-2.0。
- 合成演示集按其清单中的 CC0-1.0 声明使用；腾讯 PDF 及 Apple/Microsoft/NVIDIA 官方披露仍归各来源及相关权利人所有。本项目记录来源、哈希和有限短摘录不代表取得对完整材料的再分发授权。
- `data/cache/` 已被 `.gitignore` 整体排除。PDF 与生成的缓存清单只用于本机复现，**不随 Git 仓库、提交包或发布产物分发**；可跟随仓库的是官方链接和来源元数据。
- 运行者应自行确认下载、缓存、引用短摘录及展示结果是否符合来源网站条款、版权和所在司法辖区要求。结果中的页码与短引文只用于可审计溯源，不能替代或复刻完整报告。

## 6. 质量控制、已知限制与责任使用

- 哈希保证所用字节未变化，但不证明内容真实、完整或法律上可自由使用。
- `published_at` 是清单提供的文档级日期；系统尚未建模更正公告、版本链、盘中可得性和不同市场时区。
- PDF 表格抽取可能打乱列标题、脚注和阅读顺序。系统保留页码并附加附近表头，但关键数值仍应回看官方 PDF。
- 当前评测未提供语义裁判时，FACT 只有逐字证据 span、DERIVED 只有规范化的已执行计算投影可以获得事实信用；lexical overlap 仅保留为诊断字段，不参与事实信用。无金标要点集时，完整性仍只是结构性检查。
- 三公司挑战偏向大型科技企业，且由 AI 策展；不得以历史 3/6→6/6、当前 0/6→6/6 或 3/3 负例宣称跨行业、held-out 或真实生成泛化。
- 所有演示输出仅用于研究与软件验证，不构成财务、法律或投资建议；涉及真实决策时必须由具备资质的人复核原始披露、口径和计算。

## 7. 本地复现与完整性检查

在项目目录执行：

```bash
python scripts/download_public_reports.py
sha256sum data/cache/tencent/*.pdf
PYTHONPATH=src python scripts/run_postfreeze_challenge.py --verify-only
PYTHONPATH=src python scripts/run_postfreeze_challenge.py
python scripts/verify_submission.py --compact
```

下载结果应与上表一致。`verify_submission.py` 会独立解析六类挑战账本、重算当前可验证文件哈希、核对嵌入 manifest 与两条 failure→repair 链，而不只信任结果 JSON 的自报字段。不要对 `data/cache/` 使用强制加入版本控制，也不要把其中 PDF 打包进提交物。
