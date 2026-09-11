# 腾讯财报演示记录

`TC01_demo.json`是供完整演示使用的独立Hy3修订记录。基于原TC01的已核验财报证据，重新检查业务合计与子项口径，并生成简洁研究结论；随后重新调用Hy3评判，评分与新答卷哈希绑定。

原始12题回归、各版回答和所有对照统计保持不变。本记录不计入原实验均值，也不是新增的独立问题。`revision_protocol.json`保存完整修订输入、提示、源记录哈希和适用范围。

在工作台选择“回放原生PDF实测”，再选择“TC01 · 研究简报演示”即可查看与完整视频相同的记录。

离线核验：

```bash
python scripts/verify_demo_record.py
```

重新调用Hy3需按项目README配置环境变量，并取得登记的腾讯2025Q2原PDF。以下命令将新响应保存在独立空目录，产生模型调用费用：

```bash
python scripts/run_demo_revision.py --execute \
  --pdf data/cache/native_expansion/tencent25q2.pdf \
  --output results/demo_reproduction
```

已保存结果、提示与关键代码可以核查；在线生成可能随供应商模型变化，重新运行不保证逐字或逐分一致。
