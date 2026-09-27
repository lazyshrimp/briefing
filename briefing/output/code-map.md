# 代码对照

按实现计划第 2 节，把现有读取逻辑和不能调用的函数对照到 `briefing/`。处置只有 `copy`、`new`，Stockbee 的 25% 与成交额过滤单独标为不可复用。

| 项 | 现有符号 | 处置 | 落到 |
| --- | --- | --- | --- |
| 日线记录 | `_day_record_dtype`、`_read_day_tail` | copy | `briefing/tdx/day.py` |
| 沪深A股日线枚举 | `_iter_a_share_day_files` | copy | `briefing/tdx/universe.py` |
| 指数日线 | `get_index_kline_from_tdx`、`_INDEX_SYMBOL_MAP` | copy | `briefing/tdx/day.py` |
| 扩展数据 | `_get_extdata_dir`、`_read_extdata_series` | copy | `briefing/tdx/extdata.py` |
| 50日线以上家数 | `get_market_breadth_ma50_from_tdx` | copy | `briefing/tdx/extdata.py` |
| 家数分母 | `_count_a_shares_from_lday`、`_count_block_members` | copy | `briefing/analysis/ma50.py` |
| 行业代码表 | `_load_stock_to_block_mapping`、`tdxzs.cfg`、`incon.dat` | copy | `briefing/tdx/blocks.py` |
| 概念代码表 | `_load_concept_membership` | copy | `briefing/tdx/blocks.py` |
| Stockbee 25%与成交额过滤 | `get_stockbee_breadth_from_tdx` | 不可复用 | `briefing/analysis/breadth.py` 按 60 个交易日前收盘价另写，不用其 25% 和流动性过滤 |
| 52周新高扫描 | `src/services/new_high_scanner_global.py` | new | `briefing/tdx/extdata.py` 的 `read_new_high_net` |
| 情绪评分 | `src/services/report_builder.py` | new | `briefing/report/sentiment.py` |
