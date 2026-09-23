# AGENTS.md

面向在本仓库工作的 coding agent。只记录**读代码不容易推出来**的约束；`ls` 能看到的东西不重复。

## 这个项目是什么

每期只出 **1 注**的超级大乐透选号工具：在用户给的排除池里随机组 1 注，再让它通过「历史关 + 前区关 + 后区关」三道筛选（13 条规则 + 历史杀号）。附带数据表增量更新、反向筛号器、开奖对账、按期查号。

它是一个**形态过滤器 + 数据处理工具**，不是预测工具。任何改动都不得让仓库看起来像在承诺中奖效果。

## 核心机制（不读代码看不出来的部分）

- **出号与筛号共用同一套判定，不要各写一遍**。`dlt_pick_one.py` 的过筛**不是**自己实现的，它直接调用 `filter_check.gates()`。`filter_check.py` 内部另有一份“逐条规则镜像”（`front_report()` / `back_report()`）**只用于报告是哪条规则挡住的**。
- **镜像与引擎之间有 drift 一致性断言**。`filter_check.check_one()` 会同时跑镜像和引擎，二者口径分叉时当场告警（见 `filter_check.py` 中 `drift = ...`）。所以**改规则必须两边同步**，否则运行时会报 drift，而不是悄悄出两套结果。
- **随机的正确性靠“抽到不过就重抽”，不是“先枚举全部合法组合再均匀抽”**。两者分布等价，前者实现简单且不必枚举 C(35,5)×C(12,2) ≈ 2100 万种组合。不要为了“更均匀”改成枚举方案。
- **判定第 N 期时，历史数据严格只取第 N 期之前**。历史 / 2026 历史 / 冷号 / 上期号四个上下文都遵守这条。测试里有专门一条守着“上下文不含目标期及之后数据”——改 `build_ctx()` / `load_history()` 时不许破坏它。
- **「主开关」是文本正则读取的，属于脆弱契约**。期号只在 `dlt_pick_one.py` 顶部写一次（`CURRENT_PERIOD = "26109"`），其余脚本的默认期号都经 `paths.read_main_switch()` 从那一行读。**按文本正则匹配**，所以写法定死为 `CURRENT_PERIOD = "NNNNN"`。改成 f-string、常量表或从配置读，会让所有脚本的默认期号静默失效。
- **规则是有历史的，不是凭空定的**。后区跨度规则（原 ≤ 7）已**整条取消**：该阈值在全历史误杀 428 期（14.6%），是全部规则里最狠的一条。前区冷号阈值 `COLD_INTERVAL = 5` 已停用，该常量现在只用于概况里的冷号统计；后区冷号阈值放宽到 `BACK_COLD_INTERVAL = 8`。**动阈值前先读 [docs/rules.md](docs/rules.md) 的误杀统计，动完要同步更新该文档。**
- **三道关是形态过滤，不改变中奖概率**。README 记录的“约 78% 联合通过率”指的是**抽一注能过筛的概率**，不是任何中奖率。两者不要在文档或代码注释里混用。
- **产出文件默认写在当前目录，且已 gitignore**：`我的_<期号>_1注.txt`（每行一注，`#` 开头为注释）与 `出号记录.txt`（追加式台账：期号 / 出号时间 / 号码 / 前后区排除 / 尝试次数 / seed）。用户的投注记录不进版本库。
- **数据表查找是三级的**（`paths.find_data_file()`）：① `DLT_DATA` 环境变量 → ② `<仓库根>/data/大乐透历史开奖数据.xlsx` → ③ `<当前工作目录>/大乐透历史开奖数据.xlsx`，第一个命中的被采用。不要硬编码数据表路径 —— `paths.py` 的职责就是去硬编码。
- **脚本可从任意工作目录运行**：`filter_check.py` 会把脚本自身目录插到 `sys.path` 首位（否则同目录 `import lottery_core` 会失败），并把 `stdout` 重配为 `utf-8`。新增脚本请沿用这两行，否则中文输出在 Windows 上会乱码。

## 常用命令（已在本仓库源码核实）

```bash
pip install -r requirements.txt

python update_excel.py                      # 增量更新数据表（唯一需要联网的脚本）
python update_excel.py --check              # 只做数据表自检，不更新
python update_excel.py --dry-run            # 只列出要补的期次，不写文件
python update_excel.py --no-fetch           # 不联网，只用 NEW_DRAWS 手工补录
python update_excel.py --pages 3            # 抓取页数（默认 3 页 = 300 期）
python update_excel.py --snapshot           # 另存快照

python dlt_pick_one.py -ef 4,9,13 -eb 3,5   # 出 1 注
python dlt_pick_one.py --period 26109 --seed 42 --outdir .   # 指定期号 / 复现 / 落盘目录

python filter_check.py                      # 看本期筛选概况 + 冷号/遗漏
python filter_check.py "08 09 10 11 25 + 04 12"
python filter_check.py --file 注单.txt
python filter_check.py --period 26108 08,09,10,11,25,04,12

python check_result.py "01 05 07 21 35 + 01 04" --file 我的_26109_1注.txt
python check_result.py "开奖号" --file 注单.txt --pool-big   # 奖池 ≥8 亿的上浮口径
python show_period.py 26080 26076
python -m unittest discover -s tests -v
```

改动后的最小验证：`python -m unittest discover -s tests -v`。

## 改动纪律

- **规则判定只改 `lottery_core.py`**（`check_front_all()` / `check_back_all()` / `is_bet_safe()` 等纯函数），然后**同步** `filter_check.py` 里用于展示的 `front_report()` / `back_report()` 镜像。不同步会触发 drift 告警。
- **`lottery_core.py` 必须保持纯函数、无副作用**：不读环境变量、不写文件、不联网。数据读取属于 `paths.py` 与各 CLI 脚本。
- **每个新规则/新阈值都要配一个“只违反它”的测试样本**。现有测试的组织方式就是这样（奖金表全档位、每条规则各一个反例、历史杀号四种撞法、随机一注必过三关、无未来信息）。
- **奖金表改动要覆盖两档口径**：奖池上浮（≥8 亿，`--pool-big`）与基准档。
- **正则是脆的**：`CURRENT_PERIOD` 的文本正则是外部契约，改它属于破坏性变更。
- **文档与代码要一起动**：改规则 → 同步 `docs/rules.md` 的统计；改参数 → 同步 `README.md` 的命令速查表与 `llms.txt`。
- **不要改动 `data/大乐透历史开奖数据.xlsx`** 的结构（10 列固定布局、第 1 行表头、第一个工作表）；下游全部按列位读取。
- 不要为这个仓库引入 `openpyxl` 之外的第三方依赖。当前唯一依赖是 `openpyxl>=3.0`。

## 模块速览

| 路径 | 职责 | 关键点 |
| --- | --- | --- |
| `dlt_pick_one.py` | 主脚本：排除池随机 1 注 + 三关过筛 | **主开关宿主**（`CURRENT_PERIOD`）；过筛调用 `filter_check.gates()` |
| `lottery_core.py` | 规则引擎：13 条规则 + 历史杀号 + 奖金表 | **纯函数、无副作用**；阈值常量都在这（`COLD_INTERVAL`、`BACK_COLD_INTERVAL`、`PRIMES`） |
| `filter_check.py` | 筛号器：单注/批量过筛 + 概况 | 含 `gates()` / `check_one()` 与 `front_report()` / `back_report()` 镜像 + drift 断言 |
| `update_excel.py` | 数据更新：官方接口增量补齐 + 自检对账 | 唯一联网脚本；手工补录走 `NEW_DRAWS` + `--no-fetch` |
| `check_result.py` | 开奖对账：算奖级与奖金 | `--pool-big` 切上浮口径 |
| `show_period.py` | 按期号查开奖号 | 可传多个期号 |
| `paths.py` | 路径与数据源解析 | `find_data_file()` 三级查找；`read_main_switch()` 正则读主开关 |
| `data/大乐透历史开奖数据.xlsx` | 历史开奖数据表 | 10 列固定布局，勿改结构 |
| `docs/rules.md` | 每条规则的依据、放宽记录与筛选统计 | 改规则必须同步 |
| `tests/test_rules.py` | 单元测试（规则边界 + 端到端） | **未覆盖**真实网络抓取与 Excel 样式修补 |

## 不要做的事

- **不要把它写成或说成预测工具**。不要引入走势预测、频次加权、遗漏值加权、“专家号”、机器学习选号。不要承诺或暗示任何中奖率提升。
- **不要改成多注**。一套流程固定就是 1 注；不要为了“提高覆盖面”加注或多期合并。
- **不要自动下注、不要接入任何投注平台**，不要写任何提交投注单的代码。
- **不要在没有更新 `docs/rules.md` 统计的情况下改规则阈值**（尤其不要把已取消的后区跨度规则、已停用的前区冷号阈值“补回来”）。
- **不要单独改 `lottery_core.py` 而不同步 `filter_check.py` 的镜像**，也不要删掉 drift 断言或把它降级成静默日志。
- **不要破坏“不使用未来信息”**：判定第 N 期时不得让第 N 期及之后的数据进入上下文。
- **不要硬编码数据表路径**，也不要在 `lottery_core.py` 里读环境变量或文件。
- **不要提交用户的产出文件**（`我的_*.txt`、`出号记录.txt`）或任何真实投注记录；它们已在 `.gitignore` 里，不要为了“方便演示”把它们加进来。
- **不要改数据表结构**、不要重排列顺序、不要改工作表名。
- **不要引入新的第三方依赖**（当前仅 `openpyxl`）。
- **不要在文档里写具体到个人的购彩建议**；本仓库的定位是数据处理工具。
