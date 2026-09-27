# 影响分析

简报单独成程序，只读通达信目录和手工情绪表。

## 新增范围

新增代码都在 `briefing/`：`core/`、`tdx/`、`analysis/`、`report/`、`evaluation/`、`workflow/`、`skills/`、`agents/`、`tests/`。每日入口是 `briefing/workflow/daily.py` 的 `run_daily`。失败诊断在 `briefing/agents/diagnostic.py` 和 `briefing/skills/diagnose.py`，不插进通过的每日路径。

## 只读目录

行情只读 `C:\zd_pazq_hy` 的日线、扩展数据和板块代码表。情绪历史读 `briefing/data/sentiment.csv`。这两个位置都不在本程序里改写行情。

## 不改动的 canslim 部分

`D:\canslim_standalone` 的选股与仓位逻辑保持原样。不调用 `get_stockbee_breadth_from_tdx`，也不把 canslim 报告里的家数当作本程序的期望值。
