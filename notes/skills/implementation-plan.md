# Implementation Plan

日期：2026-09-22  
收口：2026-09-23（只改本计划，不改两份只读规格）  
收口修订：2026-09-23。区分 Diagnose Skill 与 Diagnostic Agent，修正评论校验、D6/D7 重跑和状态语义。同日再次收口：Skill 只保留两个；目录按业务模块组织，不设 `tools/`。不改两份只读规格。  
已确认口径（详见第 12 节）：2026-09-23 由人指定：停牌当日成交量为 0 的不计入当天 4% 和 25% 家数；ST 保留；4% 用该股自己的上一根 K 线；50 日线比例的分母按规格 3.2，不缩小。2026-09-24 由人指定：新高减新低直接读通达信 `extdata_13`，不另给新高家数和新低家数（需求 3.2 已同步修订）；60 日 25% 按沪深300交易日历往前数 60 个交易日，基准日没有 K 线的不计入涨跌家数；沪深与创业板分母取行情列表 `specgpext.txt`。  
只读规格：`notes/skills/requirement-analysis.md`  
只读流程：`notes/skills/briefing-workflow-design.md`  
本文件是交给开发阶段执行的计划。批准前不写实现代码。

批准：2026-09-24 批准，按第 11 节顺序实现。

新程序放在本仓库 `briefing/`，运行时不 import `D:\canslim_standalone`。canslim 只作为阅读参考。不修改 canslim，不修改两份只读规格。

## 1. Implementation Scope

本次实现包含：

- 一个独立程序：交易日收盘、通达信数据更新之后，生成一份带日期的 A 股简报。
- 规格里的五块：沪深300与创业板指信号、广度、情绪数字和图、市场评论、板块与概念前 10。
- 对照需求第 4 节 11 条的 Evaluator。实现自检另列，不算新增需求。
- 开发阶段的读取、计算、测试。Evaluator 为 FAIL 时，Diagnostic Agent 只收集证据并给出诊断。Diagnose Skill 只根据已给证据分类。改代码由 Human Fix 完成。

本次实现不包含：

- 自动下单、买卖价、仓位建议。
- 个股榜、风格榜、地区榜、大盘类 880 指数榜。
- 修改 `requirement-analysis.md` 或 `briefing-workflow-design.md`。
- 把 canslim 的选股、买卖、仓位逻辑抽进来或改掉。
- 在通达信盘后文件未更新时改用其他行情源。



## 2. Repository / Existing Code Analysis



### 需要复用的读取逻辑

从 `D:\canslim_standalone\data_provider\tdx_provider.py` 复制读取方式到 `briefing/`，不作为库依赖。


| 现有符号                                                                | 文件                | 新程序里的用途           | 数据来源                                               |
| ------------------------------------------------------------------- | ----------------- | ----------------- | -------------------------------------------------- |
| `_day_record_dtype`、`_read_day_tail`                                | `tdx_provider.py` | 解析 32 字节日线        | `vipdoc/**/lday/*.day`                             |
| `_iter_a_share_day_files`                                           | 同上                | 枚举沪深 A 股日线，不含北交所  | `sh6*.day`、`sz0*.day`、`sz3*.day`                   |
| `get_index_kline_from_tdx`、`_INDEX_SYMBOL_MAP`                      | 同上                | 读沪深300、创业板指       | `sh000300.day`、`sz399006.day`                      |
| `_get_extdata_dir`、`_read_extdata_for_stock`、`_read_extdata_series` | 同上                | 读 RPS 与 50 日线以上家数 | `T0002/extdata/extdata_{N}.idx/.dat`               |
| `get_market_breadth_ma50_from_tdx`                                  | 同上                | 三个 50 日线以上比例的读取方式 | `extdata_4` 沪深 A，`extdata_5` 沪深300，`extdata_6` 创业板 |
| `_count_a_shares_from_lday`、`_count_block_members`                  | 同上                | 比例的分母             | 日线文件计数、板块成分                                        |
| `_load_stock_to_block_mapping`、`tdxzs.cfg`、`incon.dat`              | 同上                | 行业板块代码与名称         | `T0002/hq_cache/tdxzs.cfg`、安装根目录 `incon.dat`       |
| `_load_concept_membership`                                          | 同上                | 概念板块代码与名称         | `T0002/hq_cache/infoharbor_block.dat` 中 `#GN_`     |




### 不能直接调用的现有函数

`get_stockbee_breadth_from_tdx` 不调用。

- 它默认 `min_amount = 10_000_000`，会丢掉成交额不足的股票。需求第 3.2 节没有成交额过滤。
- 它的 25% 是相对 `quarter_window`（默认 65）日最高价、最低价。需求是相对 60 个交易日前的收盘价，涨幅 ≥ 25% 或跌幅 ≤ -25%。
- canslim 报告里的 `834 / 46` 来自这套口径，不能当作本程序的期望值。

`src/services/new_high_scanner_global.py` 不调用。它扫的不是本需求的沪深 A 股收盘价 52 周新高。

`src/services/report_builder.py` 的 sentiment 是另一套评分，不调用。

### 需要新增的代码

不设 `briefing/tools/`。Tool、Skill、Workflow、Agent 是架构角色，不是顶层目录。

```text
briefing/
├── core/
│   ├── calendar.py          # is_trading_day
│   └── models.py            # snapshot、draft、评论结构
├── data/
│   └── sentiment.csv
├── tdx/
│   ├── day.py               # read_day_bars
│   ├── extdata.py           # read_extdata_series、read_block_rps
│   └── blocks.py            # load_industry_blocks、load_concept_blocks
├── analysis/
│   ├── signals.py           # index_signals
│   ├── breadth.py           # breadth_snapshot
│   ├── ma50.py              # ma50_ratios
│   └── ranks.py             # daily_top10、rps_top10
├── report/
│   ├── sentiment.py         # append_sentiment、render_sentiment_chart
│   ├── commentary.py        # write_commentary
│   └── writer.py            # write_briefing
├── evaluation/
│   └── evaluator.py         # evaluate_briefing
├── workflow/
│   └── daily.py             # run_daily，D1–D7
├── skills/
│   ├── compute_snapshot.py
│   └── diagnose.py
├── agents/
│   └── diagnostic.py
├── tests/
│   └── fixtures/
├── output/
└── main.py
```

`analysis/` 不再拆成 `index/`、`breadth/`、`ranking/`。`output/` 只放生成的简报和图。

### 架构角色和目录

两者不是一回事。

- `tdx/day.py`、`analysis/signals.py` 里的函数是 Tool，因为每个函数做一件确定的事。不因此建立 `tools/`。
- `workflow/daily.py` 是 Workflow，因为它固定编排 D1 → D7。
- `agents/diagnostic.py` 是 Agent，因为失败之后下一步读什么还不固定时，由它决定。
- `skills/compute_snapshot.py` 和 `skills/diagnose.py` 是 Skill，因为它们各封装一套可复用方法。
- `evaluation/evaluator.py` 是 Evaluator。

### 组件归属

Runtime，由 `workflow/daily.py` 的 `run_daily` 调用：

- `core/`、`tdx/`、`analysis/`、`report/`、`evaluation/` 中的每日函数
- `skills/compute_snapshot.py`

Development Activity，不进入 `run_daily`，也没有对应的 Skill 文件：

- 读取规格
- `code_understanding`：建立需求到现有代码的对照
- `impact`：分析修改范围和边界
- `implementation_plan_check`：批准前核对计划是否可执行
- `review`：对照规格检查实现差异

Failure diagnosis path，不是 D1–D7 主路径：

- `agents/diagnostic.py`
- `skills/diagnose.py`

`run_daily` 不读取 `requirement-analysis.md`。

## 3. Data Sources



### 通达信数据

- Input：本地已收盘的日线与扩展数据。
- Location：`C:\zd_pazq_hy`。
- Format：`.day` 为 32 字节小端记录，`date/open/high/low/close` 为无符号整数，价格除以 100。`extdata_{N}.idx` 每条 29 字节，`extdata_{N}.dat` 每条 12 字节。板块名称在 `tdxzs.cfg`、`incon.dat`、`infoharbor_block.dat`（GBK）。
- Required Fields：日线的 `date`、`close`；指数还要足够长的收盘序列以计算 20 日、20 周、52 周。扩展数据要能取出每个板块代码在目标日的排名值。
- Validation：文件存在；最后一根 K 线日期等于目标交易日；价格除以 100 后为正。否则该项为 MISSING，或整次 STOP。状态定义见第 6 节。



### C:\zd_pazq_hy

- Input：通达信安装目录，盘后已更新。
- Location：
  - `vipdoc/sh/lday/sh000300.day` 沪深300
  - `vipdoc/sz/lday/sz399006.day` 创业板指
  - `vipdoc/sh/lday/sh6*.day`、`vipdoc/sz/lday/sz0*.day`、`vipdoc/sz/lday/sz3*.day` 沪深 A 股
  - `vipdoc/sh/lday/sh880*.day` 板块指数
  - `T0002/extdata/extdata_4.dat`、`extdata_5.dat`、`extdata_6.dat`
  - `T0002/extdata/extdata_11.dat`、`extdata_7.dat`、`extdata_12.dat`、`extdata_8.dat`
  - `T0002/hq_cache/tdxzs.cfg`、`tdxhy.cfg`、`infoharbor_block.dat`
  - 根目录 `incon.dat`
- Format：见上一节。不读 `vipdoc/bj`。不把 `extdata_13` 当作当日板块排名。
- Required Fields：目标日有 K 线；行业与概念都能把 880 代码映到名称；RPS 文件含该板块代码。
- Validation：目录存在且目标日指数 K 线日期匹配。目录不存在或指数日期落后于目标日 → 停止，不换源。



### D:\canslim_standalone

- Input：只读源码，供开发时对照读取格式。
- Location：`data_provider/tdx_provider.py`。
- Format：Python 源码。
- Required Fields：无运行时字段。
- Validation：开发机上该文件可读。运行简报时不访问这个目录。其中 Stockbee 的 4% 与 25% 结果不得写入测试期望值。



### 情绪手工数据

- Input：人每周填入的看涨、看跌、横盘百分比，以及数据日期。
- Location：`briefing/data/sentiment.csv`。历史行可以从 `D:\investor_sentiment_chart\market_sentiment_full_data.csv` 导入日期、看涨、看跌、横盘。导入时重算多空差，不沿用原文件的多空差列。
- Format：CSV，表头 `date,bull,bear,flat`。百分比用小数或「33.0%」均可，读入后归一成百分数。
- Required Fields：`date`、`bull`、`bear`、`flat`。
- Validation：三个百分比之和与 100 的差不超过 1 个百分点。多空差 = 看涨 − 看跌。同一日期重复写入 → 拒绝新行并停止该周更新。本周无新行 → 沿用上一周且不新作图。



## 4. Tools

下面每一项都是 Tool：一次调用完成一件确定的动作。实现落在第 2 节的业务模块里，不为此新建 `tools/`。

`read_requirement` 不是运行时 Tool，也没有模块。开发时直接阅读规格文件。`run_daily` 不调用它。

### is_trading_day

- Name：`is_trading_day`
- Purpose：判断目标日是否交易日。
- Input：`date`、`sh000300.day` 路径。
- Output：`trading_day` 或 `skip`。
- Failure Mode：指数日线不存在或无法解析 → `stop`，不是 `skip`。
- Validation：文件最后若干日期中含目标日则为交易日，否则 `skip`。



### read_day_bars

- Name：`read_day_bars`
- Purpose：读一只证券的日线收盘序列。
- Input：`.day` 路径，可选最后 N 根。
- Output：按日期升序的 `{date, close}` 列表。`close` 已除以 100。
- Failure Mode：文件缺失或记录长度不是 32 的倍数 → `missing`。
- Validation：日期递增；收盘价大于 0。



### read_extdata_series

- Name：`read_extdata_series`
- Purpose：读一份 extdata 在目标日的数值。
- Input：`extdata_{N}` 目录、代码、日期。
- Output：该代码当日的排名或计数；没有则为 `missing`。
- Failure Mode：idx/dat 缺失、代码不在索引中。
- Validation：返回值类型为数值或 `missing`，不返回空字符串冒充 0。



### load_block_maps

- Name：`load_block_maps`
- Purpose：分开装载行业板块与概念板块的 880 代码和名称。
- Input：`tdxzs.cfg`、`incon.dat`、`infoharbor_block.dat`。
- Output：`industry: [{code, name}]`，`concept: [{code, name}]`。
- Failure Mode：文件缺失 → `stop`。
- Validation：两边代码集合分别非空；风格、地区、大盘类代码不在这两个列表里。分类规则与 canslim 已使用的行业链、`#GN_` 概念头一致，不在本计划里新造分类。



### index_signals

- Name：`index_signals`
- Purpose：对一条指数收盘序列计算三个 YES/NO。
- Input：升序收盘价。日线用每日收盘。周线用每个周一到周五区间内最后一个交易日的收盘，再算 10 周、20 周均线。
- Output：`{daily_buy, weekly_buy, above_rising_ma5}`，值为 `YES` 或 `NO`。
- Failure Mode：交易日不足 20 周 → 对应信号 `missing`，不猜 YES。
- Validation：
  - Daily Buy 为 YES 当且仅当收盘 > MA10、收盘 > MA20、MA10 > MA20。
  - Weekly Buy 同理，用周收盘。
  - Above Rising 5-DMA 为 YES 当且仅当收盘 > MA5 且今日 MA5 > 前一交易日 MA5。



### breadth_snapshot

- Name：`breadth_snapshot`
- Purpose：汇总 52 周净值，计算当日 4% 家数、5 日与 10 日突破比率、滚动 60 日 25% 家数。
- Input：目标日、`load_a_share_universe` 读出的沪深 A 股日线、沪深300交易日历、`extdata_13` 在目标日的净值。不含北交所。无成交额门槛。纳入规则见第 12 节已确认第 2 条：ST 保留；统计日成交量为 0 的不计入当天家数；凑不满该项窗口的不计入涨家数、跌家数。
- Output：
  - `net`。新高家数 − 新低家数，由调用方从 `extdata_13` 读入，本函数不扫描收盘价。不输出 `nh`、`nl`。
  - `up4, down4`。涨幅 ≥ 4%，跌幅 ≤ -4%，相对前一交易日收盘。
  - `ratio5, ratio10`。含当天的家数之和相除。大于 1 的标记 `buyers_dominate`。跌家数之和为 0 时标记 `no_down_4`。
  - `up25, down25, diff25`。相对沪深300交易日历上 60 个交易日前的收盘价。差值 = 涨家数 − 跌家数。
- Failure Mode：单文件读失败 → 该项按「缺失」处理。统计日成交量为 0，或该项所需的历史收盘价不存在 → 该股不计入这一项的家数，不是写「缺失」。`extdata_13` 没有目标日 → `net` 为 `missing`，其余继续。不得用成交额门槛代替「成交量为 0」。
- Validation：`net` 等于 `extdata_13` 目标日的值，`diff25 == up25 - down25`。比率与家数之和的商一致，误差只来自四舍五入到两位小数。



### ma50_ratios

- Name：`ma50_ratios`
- Purpose：三个 50 日线以上比例。
- Input：`extdata_4/5/6` 的站上家数，以及对应分母。沪深300分母为成分股数 300。沪深分母为行情列表 `specgpext.txt` 市场 0/1 的沪深 A 股数，不含北交所。创业板分母为其中 300/301/302 开头的股票数，不是创业板指成分股。两者与 `load_a_share_universe` 使用同一份代码集合。
- Output：三个 `{above, total, pct}`。
- Failure Mode：分子或分母缺失 → 该比例 `missing`。
- Validation：`pct == above / total`，`total > 0`。



### daily_top10

- Name：`daily_top10`
- Purpose：板块、概念各自按当日板块指数涨跌幅取前 10。
- Input：`sh880*.day`、行业列表、概念列表、目标日。
- Output：两个列表，每项 `{name, code, pct}`。涨跌幅 = 最后一根收盘 / 前一根收盘 − 1。
- Failure Mode：某代码没有目标日 K 线 → 不进榜。有效指数不足 10 个 → 有多少写多少，并带 `short_list`。
- Validation：行业榜、概念榜各自按 `pct` 降序。两榜分别计算、分别排序。不要求两套分类的名称或代码互斥。风格、地区、大盘类不在这两张榜中。



### rps_top10

- Name：`rps_top10`
- Purpose：5/10/15/20 日前 10。
- Input：周期到文件的映射：5→`extdata_11`，10→`extdata_7`，15→`extdata_12`，20→`extdata_8`。以及对应区间的板块指数涨跌幅。
- Output：行业、概念各四张榜。顺序按 RPS 从高到低。每项带指数区间涨跌幅。
- Failure Mode：RPS 缺失的代码跳过。指数区间涨跌幅缺失则名称仍在，涨跌幅写 `missing`。
- Validation：排序只用来源 extdata 的 RPS 值，从高到低。指数区间涨跌幅只写在名称旁边，不参与排序，也不作为并列时的第二排序键。



### append_sentiment

- Name：`append_sentiment`
- Purpose：追加一周情绪。
- Input：`date, bull, bear, flat`。
- Output：更新后的 `sentiment.csv` 最后一行，多空差为看涨减看跌。
- Failure Mode：百分比和不在 99–101 → 拒绝写入。日期已存在 → 拒绝写入。
- Validation：新行四字段齐全，多空差等于差值。



### render_sentiment_chart

- Name：`render_sentiment_chart`
- Purpose：画最近两年的投资者情绪图。上图是深证综指，下图是多空差。
- Input：`briefing/data/sentiment.csv`，以及通达信 `sz399106.day`。
- Output：PNG 路径。
- Failure Mode：少于 1 行 → 不画，返回 `missing`。本周无新数据 → 不新作图，返回上一张图的路径。
- Validation：图中点数等于最近两年里实际画出的周数，不要求等于 CSV 的全部行数。两年以前的行留在 CSV 里。这不代替需求第 7 条的情绪块完整性。



### write_commentary

- Name：`write_commentary`
- Purpose：只根据已算出的数字写一段评论。不产生新的市场事实。
- Input：D3、D4 的结构化结果。缺失项单独传入。
- Output：`{text, metrics_used}`。`text` 是评论正文。`metrics_used` 是评论引用的指标名，每一项必须属于当日 snapshot 里允许使用的指标。不写最终 markdown，不修改已有文件。
- Failure Mode：模型不可用或超时 → 评论 MISSING，`metrics_used` 为空。内容被 Evaluator 判为 FAIL → 把拒绝原因传回，只重写一次。
- Validation：见第 9 节需求检查第 8 条。不在这个 Tool 里放行。
- Prompt 禁止：编造市场数据、涨跌幅、指数点位、成交额、市场宽度、行业或概念数据，以及 snapshot 中不存在的数值；给出买入或卖出建议、具体买卖价格、仓位建议。



### write_briefing

- Name：`write_briefing`
- Purpose：在一次 Workflow run 的 D6，把已经包含 D5 评论的 draft 写成该日 markdown。同一次 run 里只调用一次。D5 之前不得调用。不得先写带空评论槽的文件再回头改。
- Input：日期、D3 信号/广度/榜单、D4 情绪、D5 `{text, metrics_used}`。
- Output：`briefing/output/YYYY-MM-DD.md`。先写入临时文件，再原子改名到该路径。同一天再次运行时覆盖这一份，不另留历史版本。
- Failure Mode：写盘失败 → STOP，不报告已生成。评论尚未完成时调用 → STOP，不落文件。临时文件改名失败 → STOP，不把半成品留在最终文件名上。
- Validation：文件名含日期；五块标题都在；评论节来自同一次输入的 `text`。D7 尚未 PASS 时，该文件只是 candidate，不是已通过版本。



### run_tests

- Name：`run_tests`
- Purpose：运行 `briefing/tests`。
- Input：无。工作目录为仓库根。
- Output：退出码、失败用例名。
- Failure Mode：非 0 退出码。
- Validation：命令为 `python -m pytest briefing/tests -q`。



### evaluate_briefing

- Name：`evaluate_briefing`
- Purpose：D7。先跑第 9 节的 11 条需求检查，再跑同节的实现自检。自检失败不记成新的需求编号。
- Input：D6 写出的简报路径、当次 snapshot、评论的 `metrics_used`。不读 `requirement-analysis.md`。
- Output：`{pass, requirement_failures: [id], sanity_failures: [name]}`。`pass` 即 PASS。任一类非空即 FAIL。
- Failure Mode：检查程序自身抛错 → STOP，类别可标为 `evaluator_error`，不算作简报 FAIL。
- Validation：两类失败都为空才是 PASS。需求失败编号只使用 1–11。



## 5. Skills

### Skill Design Rule

- 开发步骤存在，不因此创建 Skill。
- 项目里有 Agent，不因此要求多个 Skill。
- Skill 必须是可复用的方法，不是把一次 Tool 调用包一层。
- 一次性的代码理解、影响分析、人工 Review 是 Development Activity，不自动成为 Skill。

本程序只实现两个 Skill：

- `skills/compute_snapshot.py`
- `skills/diagnose.py`

`code_understanding`、`impact`、`review`、`implementation_plan_check` 只出现在第 7 节，不创建 `skills/code_understanding.py`、`skills/impact.py`、`skills/review.py`。

### compute_snapshot

文件：`briefing/skills/compute_snapshot.py`。每日 D3 调用它。

它不是单个计算函数的包装。`index_signals`、`ma50_ratios`、`breadth_snapshot`、`daily_top10`、`rps_top10` 各自只算一块。这个 Skill 把它们收成同一份可复用的业务快照，评论、写文件和 Evaluator 都读这一份，而不是各算一遍。

- Input：D2 已经读好的原始记录。不判断交易日，不读规格文件。
- Process：按固定顺序调用上述确定性 Tool。不另写一套公式。缺一项记 MISSING，不把别的指标填进去。
- Output：D3 snapshot。每个需求字段为数值、YES/NO 或 MISSING。不含评论，不含最终 markdown。
- Validation：字段齐全；`net` 来自 `extdata_13`；`diff25 == up25 - down25`；RPS 榜的顺序来自 extdata，不按涨跌幅重排。
- Error Handling：单项 MISSING 继续。通达信目录或目标日指数日期不匹配 → STOP。

### diagnose

文件：`briefing/skills/diagnose.py`。它不是 Agent，也不是 `read_file` 或 `search_code` 的包装。读文件只是取证动作；这个 Skill 的价值是固定的失败分类方法和证据清单。

- Input：Evaluator 的 failure。若 Diagnostic Agent 已经附加了补充证据，一并传入。
- Process：使用固定 taxonomy：`wrong_file`、`formula_mismatch`、`commentary_violation`、`data_missing`、`evaluator_error`。按失败编号走预定义清单，例如信号失败看 `analysis/signals.py` 与指数日线，4% 或 25% 失败看 `analysis/breadth.py`，评论失败看 `metrics_used` 和正文。清单写明要看的模块和字段。Skill 不在清单之外临时决定「再去读一个没写过的文件」。
- Output：`failure_category`、`evidence`、`affected_function` 或 `affected_module`、`repair_suggestion`。
- Validation：类别必须是 taxonomy 之一。返回后工作区 diff 为空。测试喂入同一种 failure 时，分类和所查模块稳定，而不是返回文件原文。
- Error Handling：`evaluator_error` 对应 STOP，不算简报 FAIL。其余交给 Human Fix。同一失败项达到第 10 节上限后不再重复诊断。不改代码，不改规格。

清单没有覆盖、或同一失败同时符合多类时，下一步读什么由 Diagnostic Agent 决定。Agent 把补充证据交回这个 Skill，仍由 Skill 按 taxonomy 给出诊断。

### Diagnostic Agent

文件：`briefing/agents/diagnostic.py`。它不是 Skill，也不在 D1–D7 主路径上。

- Problem：Evaluator 为 FAIL，且预定义清单不足以确定下一条证据时，决定再查什么。
- Input：Evaluator 的 failure。
- Process：只在清单不够用时选择 `read_file`、`search_code`、`git_diff`、`git_status`。然后调用 `diagnose_failure`。不改代码，不改简报数字，不改规格。
- Output：与 Diagnose Skill 相同的结构化诊断，并带上 `affected_files`、`affected_functions`。
- Validation：诊断结束后 `git diff` 为空。
- Error Handling：Human Fix 改代码，然后重跑 Workflow。

workflow-design 里诊断之后的「修改对应处」，执行者是 Human Fix。

## 6. Runtime Workflow

Development Order 不等于 Runtime Workflow。本节只回答每天真正跑简报时的顺序。第 7 节是开发时要实现的步骤，第 11 节是建议的编码先后。三者不要混用。

日常路径保持确定性，不把 D1–D7 改成 Agent。Agent 只出现在 Evaluator FAIL 之后的诊断。

### 状态语义

全文只用下面五个状态。大小写不同仍是同一个状态。简报正文里的「缺失」是展示文字，对应 MISSING。`trading_day`、`buyers_dominate`、`no_down_4`、`short_list` 是字段值，不是这五个状态。


| 状态      | 含义                    |
| ------- | --------------------- |
| PASS    | 当前步骤或检查成功             |
| FAIL    | 步骤已经执行完，结果不符合要求       |
| MISSING | 数据或输入缺失，不是程序错误        |
| SKIP    | 按 Workflow 条件，当前步骤不执行 |
| STOP    | 出现阻断问题，Workflow 必须终止  |




### 每日顺序

每一次 Workflow run：

D1 日历 → D2 读取 → D3 计算 → D4 情绪 → D5 评论 → D6 写最终简报 → D7 Evaluator

D3 由 `compute_snapshot` 编排确定性 Tool，得到一份 snapshot。D4、D5 只把情绪和 `{text, metrics_used}` 写入内存 draft。最终 markdown 只在该次 run 的 D6、且 D5 完成后写出。不得先落带空评论槽的文件，再让评论去改它。


| 每日步骤         | 角色                       | 产出                              | 状态                                  |
| ------------ | ------------------------ | ------------------------------- | ----------------------------------- |
| D1 日历        | Tool                     | 交易日则继续；非交易日为 SKIP               | 文件损坏为 STOP                          |
| D2 读取        | Tool                     | 原始记录；单条读不到为 MISSING             | 目录未更新为 STOP                         |
| D3 计算        | Skill `compute_snapshot` | 信号、广度、榜单                        | 单项可 MISSING |
| D4 情绪        | Tool                     | 情绪数字与图，写入 draft                 | 本周无新数据则沿用上一周                        |
| D5 评论        | LLM                      | draft 上的 `{text, metrics_used}` | 重写一次仍 FAIL 则评论为 MISSING             |
| D6 写文件       | Tool                     | 该日 markdown                     | 写失败为 STOP                           |
| D7 Evaluator | Evaluator                | PASS 或 FAIL                     | 检查程序抛错为 STOP                        |


`run_daily` 不调用 `read_requirement`。

### 文件生命周期

1. 同一次 Workflow run 里，D6 只写一次最终 markdown。
2. 「只写一次」指这一次 run，不是同一个日期永远只能写一次。
3. D6 成功且 D7 为 FAIL 时，该文件只是 candidate。它不是已通过版本。
4. 修复后可以重跑同一天。重跑允许覆盖该日文件。最终目录里该日期保留一份。v1 不做备份，也不做多版本管理。
5. D6 先写临时文件，再原子改名到 `briefing/output/YYYY-MM-DD.md`，避免留下半成品。
6. 重跑仍走完整的 D1–D7。新的 D6 覆盖该日文件，新的 D7 为 PASS 之后，该日输出才算完成。



### 失败后的诊断

D1–D7 全部成功并 PASS 时，不进入 Agent。

```text
Evaluator
    ↓ FAIL
Diagnostic Agent
    ↓
read_file / search_code / git_diff / git_status
    ↓
Diagnose Skill
    ↓
structured diagnosis
    ↓
Human Fix
    ↓
rerun Workflow
```

评论类 FAIL 且还没用完那一次重写时，先回 D5，不进入这条诊断链。诊断链不修改代码。Human Fix 改完后重跑的仍是同一条 D1–D7。

## 7. Development Steps

本节回答开发时要完成哪些实现步骤，以及每步怎么验证。它不是每日运行顺序。每日顺序只在第 6 节。

Step 1 到 Step 4，以及本节末尾的代码评审，是 Development Activity。它们不实现为 Skill。

D1–D7 与开发步骤的对应：


| 每日步骤         | 产出                     | 实现落在                                             |
| ------------ | ---------------------- | ------------------------------------------------ |
| D1 日历        | 交易日或 SKIP              | Step 5                                           |
| D2 读取        | 原始记录或单项 MISSING        | Step 6                                           |
| D3 计算        | snapshot               | Step 7–11，由 `compute_snapshot` 编排                |
| D4 情绪        | 情绪数字与图                 | Step 12                                          |
| D5 评论        | `{text, metrics_used}` | Step 14                                          |
| D6 写文件       | 该次 run 的 markdown      | Step 13 实现 `write_briefing`，只由 Step 17 在 D5 之后调用 |
| D7 Evaluator | PASS 或 FAIL            | Step 15                                          |


Step 1–4 属于开发/验证。Step 16 是失败诊断，不属于每日主路径。

### Step 1 — 读取需求

- Step：读取规格。
- Input：`notes/skills/requirement-analysis.md`。
- Files / Functions：无模块。直接读 `notes/skills/requirement-analysis.md`。
- Implementation：只读文本。这是 Development Activity，不是 Skill，也不是 `run_daily` 的一步。
- Output：规格字符串，仅供开发对照。
- Validation Command：`python -m pytest briefing/tests/test_read_spec.py -q`
- Expected Result：测试通过，且断言文件未被改写。`workflow/daily.py` 不读取该规格。
- Failure Handling：开发阶段失败则停止对照，不根据记忆继续。不因此中断一条已经上线的每日运行。



### Step 2 — 代码库理解

- Step：Development Activity。理解现有代码，建立需求到现有代码的对照。不创建 Skill。
- Input：规格、`tdx_provider.py`、通达信目录。
- Files / Functions：无 `skills/code_understanding.py`。结果写入 `briefing/output/code-map.md`。
- Implementation：按第 2 节对照表逐项查看源码。Stockbee 的 25% 和流动性过滤标成「不可复用」。不改业务代码。
- Output：对照表，每项为 `copy` 或 `new`。
- Validation Command：`python -m pytest briefing/tests/test_code_map.py -q`
- Expected Result：11 行都在；Stockbee 25% 标记为不可复用。测试检查的是这份文档，不是一个 Skill 模块。
- Failure Handling：通达信目录不存在 → 停止。不改规格。



### Step 3 — 影响分析

- Step：Development Activity。分析修改范围、依赖、边界和潜在影响。不创建 Skill。
- Input：对照表。
- Files / Functions：无 `skills/impact.py`。结果写入 `briefing/output/impact.md`。
- Implementation：列出新增的 `briefing/` 文件、只读的 `C:\zd_pazq_hy`、不修改的 canslim 选股与仓位。
- Output：新增范围、只读目录、不修改的 canslim 部分。
- Validation Command：`python -m pytest briefing/tests/test_impact.py -q`
- Expected Result：说明中没有「修改需求」和「更换行情源」。
- Failure Handling：测试失败则重写说明，不进入编码。



### Step 4 — 批准计划

- Step：Development Activity。人批准本 `implementation-plan.md`，并核对第 7 节每步都有 Validation Command 与 Expected Result。不创建 Skill。
- Input：本文件。
- Files / Functions：无代码。
- Implementation：无。
- Output：人的批准记录。
- Validation Command：无自动命令。未批准则不创建 `briefing/` 下的业务模块。测试可以在批准后与实现一起提交。
- Expected Result：批准之后才执行 Step 5 起。缺验证命令则不开始写代码。
- Failure Handling：退回则只改本计划，不改两份只读规格。



### Step 5 — 交易日判断

- Step：实现 `is_trading_day`。
- Input：目标日、`sh000300.day`。
- Files / Functions：`briefing/core/calendar.py`。
- Implementation：目标日出现在指数日线日期中则为交易日。
- Output：`trading_day` 或 `skip`。
- Validation Command：`python -m pytest briefing/tests/test_calendar.py -q`
- Expected Result：用指数文件里真实存在的一个日期得到 `trading_day`；用 2026-09-20 若该日无 K 线则得到 `skip`（以文件实际日期为准，测试从文件取一个缺口日，不写死星期）。文件缺失时得到 `stop`。
- Failure Handling：`stop` 结束整次运行。`skip` 不生成简报，正常结束。



### Step 6 — 通达信数据读取

- Step：实现日线、扩展数据、板块代码表读取。
- Input：`C:\zd_pazq_hy`。
- Files / Functions：`briefing/tdx/day.py`、`briefing/tdx/extdata.py`、`briefing/tdx/blocks.py`。
- Implementation：复制第 2 节的记录格式。不读北交所。不读 `extdata_13` 做当日榜。
- Output：收盘序列、RPS 值、行业与概念代码表。
- Validation Command：`python -m pytest briefing/tests/test_tdx_read.py -q`
- Expected Result：`sh000300` 与 `sz399006` 能读出升序收盘；`extdata_12` 能读出至少一个 880 代码的数值；行业列表与概念列表都不为空。
- Failure Handling：根目录不存在或指数最后日期早于目标日 → 停止。单文件坏 → 该项 `missing`，继续。



### Step 7 — 指数信号

- Step：实现 `index_signals`，对两条指数各算三次。
- Input：Step 6 的收盘序列。
- Files / Functions：`briefing/analysis/signals.py`。
- Implementation：按第 4 节 `index_signals` 的三条规则。
- Output：6 个 YES/NO 或 `missing`。
- Validation Command：`python -m pytest briefing/tests/test_signals.py -q`
- Expected Result：用构造的收盘序列覆盖 YES 与 NO。真实指数文件上，手算最后一日的 MA10、MA20 与函数结果一致。
- Failure Handling：长度不足 → 该信号 `missing`，不停止其他块。



### Step 8 — 市场广度中的 50 日线比例与 52 周家数

- Step：实现 `ma50_ratios`。52 周只取新高减新低，读 `extdata_13`。
- Input：extdata_4/5/6、extdata_13、日线分母。
- Files / Functions：`briefing/analysis/ma50.py`、`briefing/tdx/extdata.py` 的 `read_new_high_net`。
- Implementation：比例 = 站上家数 / 分母。分子用 `extdata_4/5/6`，不再按 ST 或停牌剔除。分母保持规格 3.2，不因上市不足 50 日而缩小。新高减新低直接读 `extdata_13`，不扫描收盘价，不另给新高家数和新低家数。
- Output：三个比例，以及 `net`。
- Validation Command：`python -m pytest briefing/tests/test_ma50.py briefing/tests/test_new_high.py -q`
- Expected Result：`net` 等于 `extdata_13` 在目标日的数值。缺日期则为 `missing`，4% 仍继续计算。创业板分母来自行情列表里的 300/301/302，不是 `sz3*.day` 的全部文件数。
- Failure Handling：分子或分母缺失 → 该比例 `missing`。`extdata_13` 没有目标日 → `net` 为 `missing`，4% 和 25% 继续计算。



### Step 9 — 4% 突破比率

- Step：实现当日 4% 家数与 5 日、10 日比率。
- Input：沪深 A 股日线，无成交额过滤。
- Files / Functions：`briefing/analysis/breadth.py` 的 `up4/down4/ratio5/ratio10`。
- Implementation：相对前一交易日收盘。没有前一交易日收盘价的，不计入涨家数，也不计入跌家数。统计日成交量为 0 的同样两边都不计入。ST 保留。5 日、10 日里的每一天都按同一规则计家数，再把家数相加后相除，含当天。无成交额门槛。
- Output：家数、比率、买盘占优标记或「无跌幅≥4%」。
- Validation Command：`python -m pytest briefing/tests/test_breakout_ratio.py -q`
- Expected Result：构造 5 天家数，比率等于总和之商。跌家数之和为 0 时得到 `no_down_4`，不抛除零。没有前收或当日成交量为 0 的股票不进入当天涨跌家数。ST 且涨跌达到 4% 的计入。不与 Stockbee 的 `834/46` 比较。
- Failure Handling：文件读失败按「缺失」处理。全部读取失败则该项 `missing`。



### Step 10 — 60 日 25% 涨跌

- Step：实现滚动 60 个交易日的 25% 家数与多空差。
- Input：同上日线。
- Files / Functions：`briefing/analysis/breadth.py` 的 `up25/down25/diff25`。
- Implementation：与沪深300（`sh000300.day`）交易日历上 60 个交易日前那一天的收盘价比较。涨幅 ≥ 25%，跌幅 ≤ -25%。不使用 N 日最高价、最低价，也不改用该股自己的 60 根 K 线。该日没有这只股票的 K 线，或统计日成交量为 0 的，不计入涨家数，也不计入跌家数。ST 保留。4% 仍用该股自己的上一根 K 线。
- Output：三个整数。
- Validation Command：`python -m pytest briefing/tests/test_q25.py -q`
- Expected Result：`diff25 == up25 - down25`。收盘相对沪深300日历上 60 个交易日前刚好 +25% 且当日有成交的股票计入涨家数。基准日没有 K 线，或当日成交量为 0 的，两边都不计入。
- Failure Handling：文件读失败按「缺失」处理。



### Step 11 — 板块/概念排名

- Step：实现当日榜与四档 RPS 榜。
- Input：`sh880*.day`、代码表、extdata_11/7/12/8。
- Files / Functions：`briefing/analysis/ranks.py`。
- Implementation：当日按指数涨跌幅降序。5/10/15/20 日只按对应 extdata 的 RPS 值降序。指数区间涨跌幅写在名称旁，只用于展示，不改变名次。行业与概念分开。
- Output：10 张榜（2 类 × 5 个周期）。
- Validation Command：`python -m pytest briefing/tests/test_ranks.py -q`
- Expected Result：当日榜按涨跌幅排序。15 日榜顺序与 `extdata_12` 的 RPS 值一致；即使指数涨跌幅的高低顺序不同，也不重排。风格代码不在结果中。
- Failure Handling：单代码缺数据则跳过。有效数不足 10 则短列表加 `short_list`。



### Step 12 — 情绪数据和图表

- Step：实现追加与画图。
- Input：手工三个百分比；`briefing/data/sentiment.csv`。
- Files / Functions：`briefing/report/sentiment.py`。
- Implementation：多空差只由看涨减看跌得到。图按 2026-09-26 确认的画法：最近两年、上下两栏、深证综指纵轴贴着高低点、买点和卖点的竖虚线穿过两栏。详见第 12 节已确认第 6、7 条。
- Output：CSV 行与 PNG。
- Validation Command：`python -m pytest briefing/tests/test_sentiment.py -q`
- Expected Result：示例 33.0、42.0、25.0 的多空差为 -9.0。图的点数等于这两年里画出的周数。需求第 7 条另查情绪块是否齐全、同一周是否重复出图。重复日期被拒绝。
- Failure Handling：百分比非法 → 拒绝写入并停止本周更新。无新周数据 → 沿用上一周，不新作图。



### Step 13 — 内部 draft 与 D6 写入函数

- Step：实现内存中的 briefing draft，以及只接受完整输入的 `write_briefing`。每日路径不在本步落最终文件。
- Input：D3 snapshot、D4 情绪。评论字段在 D5 之前为空。
- Files / Functions：`briefing/report/writer.py` 的 draft 组装与 `write_briefing`。draft 的结构放在 `briefing/core/models.py`。
- Implementation：draft 保存信号、广度、榜单、情绪和评论槽。`write_briefing` 要求评论槽已是 `{text, metrics_used}` 或已标记为评论「缺失」。五块标题固定。缺失写「缺失」。函数被 D5 之前调用时拒绝写盘。
- Output：draft object。测试可以在传入完整评论桩之后得到一份 markdown，用来验证格式。该测试文件不是每日产物。
- Validation Command：`python -m pytest briefing/tests/test_writer.py -q`
- Expected Result：评论槽为空时不产生 `YYYY-MM-DD.md`。传入完整评论桩后，文件名含日期，五块一次写齐，评论节等于该桩的 `text`。
- Failure Handling：写盘失败 → 停止，不声称已生成。



### Step 14 — D5 市场评论

- Step：在 D3、D4 的数字已经进入 draft 之后调用 LLM。不打开、不创建、不修改最终 markdown。
- Input：draft 中已有的数字。缺失项单独传入。
- Files / Functions：`briefing/report/commentary.py`。
- Implementation：提示词只允许引用 draft 里已有的指标，并禁止编造市场数据、涨跌幅、指数点位、成交额、市场宽度、行业或概念数据，以及 snapshot 中不存在的数值；禁止买入或卖出建议、具体买卖价格和仓位建议。缺失项不得被写成结论。结果写回 draft 的评论槽。
- Output：`{text, metrics_used}`。
- Validation Command：`python -m pytest briefing/tests/test_commentary.py -q`
- Expected Result：`metrics_used` 中每一项都能在 snapshot 找到。正文里的日期、「5日」「10日」「60日」或百分比的文字写法，不因没有逐字复制 snapshot 而失败。夹具若给出买入建议、买卖价格、仓位，或明显不属于 snapshot 的市场数值，需求检查第 8 条为 FAIL。本步结束后不新写最终简报。
- Failure Handling：见第 10 节。重写一次仍失败则评论槽写「缺失」，`metrics_used` 为空。数字留在 draft，等本次 run 的 D6 一次写出。



### Step 15 — D7 Evaluator

- Step：只检查 D6 已经一次写出的最终简报。先跑 11 条需求检查，再跑实现自检。
- Input：简报文件、当次 snapshot、`metrics_used`。不读规格文件。简报文件由 Step 13 的 `write_briefing` 写出；`metrics_used` 只用于第 8 条，Step 14 完成前由评论桩提供，第 8 条记为未检查，总状态不得为 PASS。
- Files / Functions：`briefing/evaluation/evaluator.py`。
- Implementation：只判定，不改简报，不改数字。
- Output：PASS，或 `requirement_failures` 与 `sanity_failures`。D7 为 FAIL 时，D6 文件保持为 candidate。
- Validation Command：`python -m pytest briefing/tests/test_evaluator.py -q`
- Expected Result：需求检查与自检分开断言。故意改坏一个比率时，需求失败列表包含对应的第 4 节编号。自检项不得占用 1–11 的编号。
- Failure Handling：需求编号 1–7、9–11 进入 Step 16。仅第 8 条 FAIL 则回到 Step 14 重写一次。Diagnostic Agent 不改代码。自检 FAIL 同样只出建议。



### Step 16 — 失败诊断

- Step：实现 Diagnostic Agent 和 Diagnose Skill。仅当 Step 15 的需求检查为 FAIL，且不是还要回 D5 的那一次评论重写。
- Input：Evaluator 的 failure。
- Files / Functions：`briefing/agents/diagnostic.py`、`briefing/skills/diagnose.py`。两者都不改代码。
- Implementation：清单不够用时，Agent 选择 `read_file`、`search_code`、`git_diff`、`git_status`。Skill 按第 5 节的 taxonomy 和证据清单输出诊断。Human Fix 根据建议改代码后，再重跑 Workflow 或 `run_tests`。
- Output：结构化诊断。再测结果只有在人完成修改后才有。
- Validation Command：`python -m pytest briefing/tests/test_diagnose.py -q`
- Expected Result：同一类 failure 走清单时，Skill 查看的模块稳定。清单不足时才由 Agent 再选文件。诊断前后 `git diff` 为空。类别限于第 5 节的 taxonomy。不存在 `skills/code_understanding.py`、`skills/impact.py`、`skills/review.py`。
- Failure Handling：同一编号经 Human Fix 后仍 FAIL，累计 3 次 → STOP。不改规格。3 次是本计划的建议，见第 12 节。



### Step 17 — 每日生成串联

- Step：`run_daily(date)` 严格按第 6 节的 D1–D7 调用。
- Input：日期。不读 `requirement-analysis.md`。
- Files / Functions：`briefing/workflow/daily.py`。
- Implementation：D1 到 D5 只更新内存。D6 用临时文件原子改名，每次 run 写一次。同一天重跑覆盖该日文件。D7 PASS 才把该文件视为完成。D7 FAIL 时文件仍是 candidate。
- Output：简报路径与 Evaluator 结果。非交易日为 SKIP，不生成文件。
- Validation Command：`python -m pytest briefing/tests/test_workflow_order.py -q`
- Expected Result：桩记录的顺序为 D1 → D2 → D3 → D4 → D5 → D6 → D7。空目录下，D5 完成前不存在最终 markdown。已有 candidate 时，D6 覆盖它，不另建第二个日期文件。调用记录不含 `read_requirement`。FAIL 后的诊断不出现在 PASS 的每日路径里。
- Failure Handling：任一步 STOP 则不调用后续步骤。D5 评论最终为 MISSING 时，本次 D6 仍写一次，评论节为「缺失」。

### 代码评审

这是 Development Activity，不是 Skill。实现完成后，人对照规格和本计划看 diff，列出不一致处。每一条都要指到规格句子或计划步骤。列表非空则不交付。不创建 `skills/review.py`。

## 8. Test Strategy



### 单元测试

每个 Tool 一个测试文件，用构造的短序列，不依赖全市场扫描。覆盖 YES/NO 边界、除零、`missing`、多空差、榜单排序。52 周测试断言 `net` 等于 `extdata_13` 的值，缺日期时为 `missing` 且不阻塞 4%。

### 数据验证

`test_tdx_read.py` 在本机存在 `C:\zd_pazq_hy` 时运行，否则跳过并标明 `skip`，不得改用网络行情。检查目标文件存在、日期递增、880 代码能映到名称。

### 已知交易日对照测试

选通达信日线中最后一个交易日，由人在通达信里抄录沪深300三条信号里的日线一项、当日 4% 涨跌家数、一个行业的当日涨跌幅。写入 `briefing/tests/fixtures/manual_YYYYMMDD.json` 后再跑对照。期望值不得取自 canslim 的 Stockbee 输出。

另增一份 golden snapshot：`briefing/tests/fixtures/golden_YYYYMMDD.json`。它是 regression oracle / regression fixture，不是新的需求、业务规则或规格。需求来源仍然只有 `requirement-analysis.md` 和 `briefing-workflow-design.md`。

内容是该已确认交易日的 D3/D4 结构化结果，由人对照通达信抄录后冻结。代码修改后重算 snapshot，与 golden 逐字段比较，用来发现公式、字段映射或计算回归。52 周只写 `extdata_13` 的净值。它只锁定已经人工确认过的一天。通达信重算扩展数据后，extdata 派生字段的历史值可能变化，此时由人重新核对并刷新 golden。

### 集成测试

`test_workflow_order.py` 用临时目录和桩 LLM。非交易日为 SKIP，不生成文件。交易日夹具走完 D1–D7：D5 桩返回 `{text, metrics_used}`，D6 才生成唯一一份 markdown。另测同一天第二次运行会覆盖该文件，而不是再留一份。D7 FAIL 的文件标成 candidate。

### 最终 Evaluator

`python -m pytest briefing/tests -q` 通过后，对真实最后一个交易日执行 `evaluate_briefing`。11 条需求检查全部通过，实现自检也通过，才算开发阶段完成。自检失败不算一条新的需求验收失败，但仍要修到通过才能结束开发。

## 9. Evaluator

分两层。只有「需求检查」对应 `requirement-analysis.md` 第 4 节，编号 1–11。实现自检是本计划为了防止写错程序而加的，不是新需求，失败时不得记成第 12 条或改写第 4 节。这里的 PASS / FAIL 与第 6 节的状态语义相同。

### 需求检查

1. Check：交易日收盘后得到一份带日期的简报。非交易日不生成。
  Input：日期、`is_trading_day` 结果、D6 输出目录。  
   Expected Result：交易日存在一份 `YYYY-MM-DD.md`，且该文件是 D6 一次写出的最终稿。非交易日该文件不存在。  
   Pass / Fail：条件不满足即 Fail。
2. Check：沪深300、创业板各有三条 YES/NO，规则与规格 3.1 一致。
  Input：指数收盘序列、简报中的六个字段。  
   Expected Result：六个字段都能按 3.1 的三条规则复算，结果为 YES 或 NO。  
   Pass / Fail：复算结果与简报不同，或取值不是 YES/NO，即 Fail。取不到而写成「缺失」时不在本条判 Fail，改由第 11 条检查。
3. Check：三个 50 日线以上比例都能复算。分子是收盘价高于自身 50 日均线的股票数。分母按规格 3.2：沪深300为成分股数，创业板为全部创业板股票，沪深为沪深 A 股且不含北交所。
  Input：分子、分母、简报中的比例。  
   Expected Result：简报比例与分子/分母的复算结果一致。  
   Pass / Fail：复算不一致，或创业板分母用了创业板指成分股，即 Fail。本条不使用额外容差。
4. Check：当日 4%+ 涨家数、跌家数与行情逐只核对一致。
  Input：全部沪深 A 股日线（不含北交所，无成交额过滤）、简报家数。  
   Expected Result：按已确认纳入规则重新扫描的家数与简报相同。没有前收、或统计日成交量为 0 的不计入；ST 保留。  
   Pass / Fail：整数不相等即 Fail。
5. Check：5 日突破比率等于这 5 天涨家数之和除以跌家数之和，10 日同理，并在大于 1 时标出买盘占优。跌家数之和为 0 时写「无跌幅≥4%」来自规格 3.2，本条一并核对。
  Input：最近 5 日和 10 日的每日涨跌家数、简报中的比率和标记。  
   Expected Result：比率等于家数之和的商。大于 1 时简报标出买盘占优。跌家数之和为 0 时文本为「无跌幅≥4%」。  
   Pass / Fail：商不一致，或大于 1 时没有买盘占优标记，即 Fail。
6. Check：滚动 60 个交易日的 25% 涨家数减跌家数等于简报上的多空差。分类按规格 3.2，相对沪深300交易日历上 60 个交易日前的收盘价，不用区间最高价、最低价，也不用该股自己的 60 根 K 线。
  Input：`up25`、`down25`、简报差值。  
   Expected Result：差值等于涨家数减跌家数。  
   Pass / Fail：差值不对，或实现使用了最高价最低价窗口，即 Fail。
7. Check：情绪块完整性。含手工填入的数据日期、看涨、看跌、横盘、多空差和一张图。同一周内不重复出新图。
  Input：简报情绪节、当周 PNG 是否新建。  
   Expected Result：数据日期、三个百分比、多空差、一张图都在。同一周第二次运行不新作图。多空差等于看涨减看跌，这是规格 3.3 的定义。  
   Pass / Fail：缺字段、缺图，或同一周产生了新图，即 Fail。本条不检查图是否覆盖全部历史，那是第 10 条。
8. Check：市场评论只引用当天简报里已经出现的数字，不写买卖价和仓位。LLM 不能产生新的市场事实。
  Input：`metrics_used`、`text`、D3/D4 snapshot。  
   Expected Result：第一层，`metrics_used` 的每一项都属于 snapshot 中允许使用的指标。第二层只做辅助检查：正文没有明显的买入或卖出建议、具体买卖价格、仓位建议，也没有明显不属于 snapshot 的市场数值。日期、「5日」「10日」「60日」以及百分比的文字写法，不要求逐字出现在 snapshot 里。允许「买盘占优」。  
   Pass / Fail：`metrics_used` 含 snapshot 之外的指标，或第二层发现买卖建议、买卖价格、仓位、明显的无依据市场数值，即 FAIL。第二层不是「正文每个数字都必须在 snapshot 里」；它也不是第 12 条需求。
9. Check：板块、概念的当日前 10 按板块指数当日涨跌幅排序。5/10/15/20 日前 10 的顺序与对应 extdata 排名一致，旁边的涨跌幅与通达信板块指数一致。两榜分别计算、分别排序。
  Input：两套榜、日线、extdata。  
   Expected Result：当日顺序与涨跌幅排序一致。5/10/15/20 日的名次只跟对应 extdata 的 RPS 值：5 日 `extdata_11`，10 日 `extdata_7`，15 日 `extdata_12`，20 日 `extdata_8`。旁边的指数涨跌幅与板块指数一致，但不改变名次。  
   Pass / Fail：顺序不同，或旁边涨跌幅与指数不一致，即 Fail。不因为行业与概念出现相同名称或代码而 Fail。
10. Check：情绪图覆盖范围。图包含自第一条手工记录以来的全部多空差。
  Input：情绪历史序列、图所绘制的序列。  
    Expected Result：图中的多空差序列与自第一条记录到最新一周的历史一致，不缺更早的周。  
    Pass / Fail：图只画了最近若干周、丢掉第一条以来的记录，即 Fail。本条不重复第 7 条的「有没有图、同一周是否新作图」。
11. Check：取不到的数写「缺失」，不补造。通达信盘后文件还没更新时，不改用别的数据源顶上。
  Input：一个制造出来的缺失代码；把通达信目录指到空目录的测试。  
    Expected Result：缺失格子为「缺失」。空目录时运行停止，且没有第二个行情路径的读取记录。  
    Pass / Fail：出现伪造数字或第二个数据源即 Fail。



### 实现自检

下列各项不是需求第 4 节的原文。失败记入 `sanity_failures`，名称不得使用 1–11。

- `schema`：snapshot 字段为数值、YES/NO 或 `missing`。评论为 `{text, metrics_used}`。最终文件只存在一份。
- `internal_identity`：`diff25 == up25 - down25`。这是防止写错减法，需求第 6 条已经要求多空差等于涨跌家数之差；此处只检查程序内部两个字段是否自洽。
- `display_rounding`：比率展示若四舍五入到两位小数，复算时按同一展示精度比较。需求没有写 0.01 个百分点的容忍。不得把「误差不超过 0.01 个百分点」当作第 3 条或第 5 条的通过条件。
- `chart_point_count`：图的点数等于 CSV 行数。这是检查画图没有丢点的实现手段，用来帮助第 10 条，本身不是验收原文。第 7 条不使用这个断言。
- `failure_isolation`：测试夹具一次只改坏一个需求点时，测试代码自己断言「对应编号出现在 `requirement_failures`」。这是测试写法，不是需求第 4 节的一条。Evaluator 不保证任意一份坏简报只失败一个编号。



## 10. Failure and Retry

状态词与第 6 节相同。

STOP，Workflow 终止：

- `C:\zd_pazq_hy` 不存在，或沪深300日线最后日期早于目标日（盘后未更新）。
- 交易日判断因文件损坏无法完成。这一天没有 K 线则是 SKIP，不是 STOP。
- D6 写简报失败，临时文件改名失败，或 D5 未完成时试图写最终文件。
- Evaluator 程序自身抛错。Diagnose Skill 可标 `evaluator_error`。这不是简报 FAIL。
- 开发阶段的影响分析要求改需求或换行情源。
- 同一失败项经 Human Fix 后累计 3 次仍 FAIL。

规格文件读失败只停止开发阶段的对照，不进入每日 `run_daily` 的 STOP。

SKIP 或继续：

- 非交易日：SKIP，不生成文件，Workflow 正常结束。
- 单条记录读不到：该项 MISSING，其余继续。
- 本周没有新的情绪数据：沿用上一周，不新作图。
- 评论重写一次后仍 FAIL：评论写「缺失」，本次 D6 仍写出数字简报。

D7 FAIL 之后：

```text
Evaluator
    ↓ FAIL
Diagnostic Agent
    ↓
read_file / search_code / git_diff / git_status
    ↓
Diagnose Skill
    ↓
structured diagnosis
    ↓
Human Fix
    ↓
rerun Workflow
```

- 需求检查第 1–7、9–11 条 FAIL 时走上面这条。类别可以是 `wrong_file`、`formula_mismatch`、`commentary_violation`、`data_missing`。
- `data_missing` 表示证据指向数据缺失。人可以补数据或接受「缺失」，Agent 不补造数字。
- Diagnostic Agent 和 Diagnose Skill 都不改代码。workflow-design 里的「修改对应处」由 Human Fix 执行。
- `commentary_violation` 若还没用完那一次重写，先回 D5，不进诊断。已经重写过仍 FAIL，则评论标「缺失」，不再诊断。

回到 D5（评论）：

- 仅需求检查第 8 条 FAIL。
- 只重写一次。第二次仍 FAIL 则评论为「缺失」，本次 D6 写文件。不进入无限重试。

同一天重跑：

- D6 成功且 D7 FAIL 时，已写出的文件是 candidate，不是已通过版本。
- Human Fix 之后重跑同一天，D6 覆盖该日文件。v1 不保留旧版本。
- 重跑仍是完整的 D1–D7。新的 D7 为 PASS，该日输出才算完成。

重试次数：

- 评论：1 次重写。这是 workflow-design 已写明的次数。
- 同一需求失败编号：Human Fix 后再测，上限 3 次。workflow-design 只写了「约定次数」，没有给数字。本计划取 3。这不是 Agent 自动改代码的次数。



## 11. Implementation Order

这是 Development Order：开发人员按什么顺序实现组件。它不是第 6 节的 Runtime Workflow。

每日运行始终是 D1 → D2 → D3 → D4 → D5 → D6 → D7。编码时却把评论放在读取、计算、验证和写入之后。

1. `tdx/` 的日线、extdata 与板块代码表。
2. `core/calendar.py` 的交易日判断。
3. `analysis/signals.py`。
4. `tdx/universe.py` 的沪深 A 股股票池，`analysis/` 中的 50 日线比例、52 周净值（`extdata_13`）、4% 家数与突破比率、60 日 25%。
5. `analysis/ranks.py`。RPS 名次只按 extdata 的 RPS 值；指数涨跌幅只做展示。
6. 上述各项的单元测试、已知交易日夹具和 golden snapshot。
7. 情绪 CSV 与图。
8. `core/models.py` 的 draft，以及 `report/writer.py`。写入使用临时文件再原子改名。测试必须自带评论桩；评论槽为空时不写最终 markdown。
9. `evaluation/evaluator.py` 的 11 条需求检查，先用夹具测数字条。实现自检分开写。
10. 最后实现 `report/commentary.py`，输出 `{text, metrics_used}`，并补上需求检查第 8 条。不把「正文每个数字都要逐字出现在 snapshot」写成通过条件。
11. 串联 `workflow/daily.py` 的 `run_daily`。运行顺序为 D1–D7。每次 run 的 D6 写一次；同一天重跑覆盖。52 周净值读 `extdata_13`。
12. 最后实现 `agents/diagnostic.py` 和 `skills/diagnose.py`。它们不插入 PASS 的 D1–D7。不实现 `skills/code_understanding.py`、`skills/impact.py`、`skills/review.py`。

不把评论放在读取和计算之前实现。

## 12. Open Questions / Risks

52 周口径、股票纳入规则、分母和 25% 基准日已经确认，写在下面。52 周口径由人同步修订了需求 3.2。其余各项在两份只读文档里没有写死。本计划不改需求来填这些空。

### 已确认

1. **52 周新高减新低。** 2026-09-24 确认：不自己扫描收盘价。直接读通达信 ``extdata_13`` 的市场序列，该值就是新高家数减新低家数。简报不另给新高家数和新低家数。2026-09-24 该值为 -71，与通达信选股结果 39 减 110 一致。
2. **停牌、ST、上市不足窗口。** 2026-09-23 确认，只作用于本程序自己扫描的 4% 家数和 60 日 25% 家数。52 周新高减新低改读 ``extdata_13``，不再按下面的收盘价规则扫描：
  - ST 保留在沪深 A 股范围内，不按名称剔除。
  - 统计日成交量为 0 的，不计入当天的 4% 涨跌家数、25% 涨跌家数。5 日和 10 日比率里的每一天同样处理。这不是成交额门槛。
  - 没有前一交易日收盘价的，不计入 4% 涨家数，也不计入跌家数。
  - 60 日 25% 按沪深300交易日历往前数 60 个交易日，取该股在那一天的收盘价。那一天没有 K 线的，不计入涨家数，也不计入跌家数。4% 仍用该股自己的上一根 K 线。
  - 50 日线以上比例的分子仍用 `extdata_4/5/6`，不在这份家数上再剔除 ST 或停牌。分母保持规格 3.2，不因上市不足 50 日而缩小。
  - 沪深与创业板分母取通达信行情列表 `T0002/hq_cache/specgpext.txt` 的市场 0 和市场 1。2026-09-24 确认：沪深 5227 只，最后一只是 689009；创业板是其中的 300/301/302，当时 1412 只。市场 2 的 9 开头北交所代码不计入。已摘牌、只留在日线目录里的代码不计入。
3. **60 日 25% 的基准日。** 2026-09-24 由人指定：按沪深300（`sh000300.day`）的交易日历往前数 60 个交易日。该股在这一天没有 K 线的，不计入涨家数，也不计入跌家数。不使用该股自己的 60 根 K 线。新高减新低仍只读 `extdata_13`。
4. **extdata 的股票池与历史值。** 2026-09-24 由人确认：通达信扩展数据的股票池调整为只含上证和深证，不含北证。重算后 `extdata_4` 在 2026-09-23 的值由 3353 变为 3189，以 3189 为准；`extdata_5`（99）、`extdata_6`（951）不变，索引由 4 条变为 1 条。extdata 的历史值会随通达信重算而变，重算后由人核对并刷新依赖它的 golden。
5. **行业榜用普通细分行业。** 2026-09-26 由人指定：行业是 `incon.dat` 里没有下级的 T 代码，再和 `tdxzs.cfg` 对上名称。煤炭、纺织服饰这类还有子行业的上级不进榜；煤炭开采、纺织进榜。概念榜不变。2026-09-24 的当日行业前 10 已由人对照通达信确认。
6. **情绪历史。** 2026-09-26 由人指定：从 `D:\canslim_standalone\data\market_sentiment_full_data.csv` 导入日期、看涨、看跌、横盘，写入 `briefing/data/sentiment.csv`。多空差重算为看涨减看跌，不沿用原表的多空差列。深证综指和投票人数不导入。共 229 行，2022-03-11 至 2026-09-18。原表两处与差值不一致：2026-05-15 原为 11、现为 −11；2026-06-13 原为 16、现为 17。
7. **情绪图。** 2026-09-26 由人指定，按 `canslim_standalone` 的画法，不从 2022 年的第一行画起。上图深证综指（`sz399106.day`），纵轴贴着窗口内的最低价和最高价，不从 0 起。下图多空差，橙色虚线，−22.5 与 52.5 两条阈值。每个绿点、红点各有一条竖虚线穿过上下两图。横坐标两图对齐。窗口是最近两年，当前图为 2024-09-20 至 2026-09-18，102 个点。文件是 `briefing/data/sentiment.png`。



### BLOCKING

无。

### 不阻塞其他字段，仍待确认

1. **诊断次数。** 见第 10 节。3 次是本计划建议的人工修改上限，不是规格的一部分，也不是 Agent 自动改代码的次数。
2. **评论所调用的模型接口。** workflow 只规定角色是 LLM，没有规定厂商和模型名。实现时把接口留在 `write_commentary` 的一个可替换参数里。未配置时按评论失败处理，不改数字。



## 13. v1 Boundary

v1 用最少的工程复杂度走通 Tool、Skill、Workflow、Agent、Evaluator 和 Human。

v1 使用：

- Python functions
- pytest
- 确定性 Tool
- Skill 作为可复用方法，v1 只有 `compute_snapshot` 和 `diagnose`
- 一个 LLM 接口，只写市场评论
- 一个 Diagnostic Agent，只做失败诊断
- Evaluator
- Human Fix 与人工确认

v1 不做：

- LangGraph
- MCP
- Multi-Agent framework
- 按 Tool / Skill / Workflow / Agent 各建一层顶层目录
- 为代码理解、影响分析、评审单独建 Skill
- 自动改代码
- 自动部署
- 自动改需求
- 自动改规格
- 复杂的 Agent 记忆
- 向量数据库
- 额外的编排框架

不追求 Agent 的数量或框架复杂度。