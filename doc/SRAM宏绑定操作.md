# 加速器 SRAM 宏绑定

## 当前状态（2026-10-30）

CPU 行为存储器指令回归已完成：67/67，通过时保留了仿真 DIV/REM 参考计算修正。
这不验证加速器 SRAM 宏。

加速器默认 `kwt_encoder_12` 的逻辑存储需求：

| 对象 | 深度 × 位宽 | 个数 |
|---|---|---:|
| 本层权重 | 1024 × 16 | 16 |
| bias / multiplier | 1024 × 16 | 4 |
| 输入激活 | 1024 × 16 | 8 |
| 合并 K/V | 1024 × 16 | 8 |
| 层间传递 | 4096 × 16 | 1 |
| 合计 | 80 KiB | 37 |

`kwt_mem16` 的契约是同一上升沿进行独立地址的一次读、一次写，读延迟一拍。
`kwt_packed_sram` 在连续局部写时同时读下一次更新的旧字和提交上一次更新，
因此不能直接换成单端口宏，也不能把一个双端口宏的两个地址绑在一起。
其连续同址写依靠已有 forwarding；实际宏对同址读写输出的处理也需要验证。

服务器首次检查已返回：有 `RAMTP128X16`、`RAMTP1024X16`，4096 深度仅见
单端口 `RAMSP4096X16`，未见 `RAMTP4096X16`。因此逻辑 4096×16 采用 4 个
`RAMTP1024X16` 深度拼接，最终方案是 **40 个物理双端口宏，80 KiB**。
使用两个地址高位解码、读 bank 编号随读时钟寄存；读延迟保持一拍。

`rtl/kwt_foundry_sram16.v` 已实现该结构，也支持直接实例化 128、1024 深度宏。
服务器第二次检查已确认控制逻辑，`rtl/kwt_sram_pins.vh` 已补全：

| 引脚 | 配置 |
|---|---|
| CLKA / CLKB | 同一上升沿时钟 |
| CENA / CENB | 低有效；B 口仅在对应 bank 写入时使能 |
| WENB[15:0] | 写入时全 0，禁止写入时全 1 |
| EMAA / EMAB | 3'd2，模型明确检查默认工作值 |
| RET1N | 1，正常工作、退出 retention |
| COLLDISN | 1，保留模型碰撞检查 |

当前服务器宏模型默认编译分支没有 `VDDCE/VDDPE/VSSE` 端口。
仿真和综合均使用逻辑端口，不定义 `KWT_SRAM_POWER_PINS`；宏模型自身的
条件编译与电源行为保持原样。综合按 Liberty 绑定，不读入 Verilog 宏行为模型。
FPGA / 原行为模型分支不依赖该配置头文件。

本地已用独立编写的契约模型通过：

- 128 / 1024 / 4096 三种逻辑深度的独立同拍读写、bank 边界和一拍读延迟。
- 打包层随机局部更新、连续同址更新、A/B/A 地址交替、零掩码、复位后数据保持。
- 契约模型故意令同址读写输出 X，检查打包层 forwarding 能正确处理。
- 显式电源端口的 supply 网接法。

十二层契约模型长回归也已通过：6,336 个输出逐位一致，3,232,909 拍，
MAC issues=1,183,248。日志在本地 `release/kwt_sram_contract_test/encoder12_fast.log`。
补全配置后基础与打包层测试已复跑通过。

**服务器真实宏功能回归现已通过**，工作目录
`~/soc/kwt_sram_20261029_150543_tqH6Fc`：三种深度适配测试、打包写/转发/复位测试
及十二层编码器全部 PASS；十二层输出 6,336 个值逐位一致、3,232,909 拍，
MAC issues=1,183,248。保留官方模型碰撞检查，使用默认逻辑端口模式。
该结果是无 SDF 的 RTL 功能回归，不是物理 setup/hold 签核。

服务器 Liberty 摘录确认单个 `RAMTP1024X16` 的 **cell area** 是
17,757.843725 µm²，40 块合计 **710,313.749 µm² = 0.710313749 mm²**。
应读取 cell 的 area，不能误取同一文件中其他层级的 `area : 1.7`。
实际综合的标准单元部分约为 255,058.04 µm²（由最新总面积减去宏面积得到），
旧的 260,027 µm² 黑盒综合数值不再作为当前面积结论。

`syn/compile_kwt_sram_libs.tcl` 已准备从官方 TT / 1.1V / 25C Liberty 生成私有 DB；
`syn/dc_compact.tcl` 已改为真实宏 link-only，要求默认配置 40 个宏、正的库面积、
没有未解析 leaf，且存在经过宏读输出的受约束时序路径。它不再补猜测的 SRAM
边界延迟。服务器库转换已成功，DC 已完成 `compile_ultra` 并加载真实 SRAM DB；
报告前的自定义检查曾将 `**logic_0**` 误判为未解析 leaf；常量检查修复后，
服务器已完整生成真实宏综合报告。当前结论是**功能与面积通过、TT setup 通过，hold 未通过**。

## 真实宏综合报告：2026-10-29

原运行目录 `~/soc/kwt_sram_20261029_150543_tqH6Fc`，报告位于
`synth_recovery_20261029_154753_xBylo9/dc_out_bound/`（以服务器实际目录为准）。

| 项目 | 结果 |
|---|---|
| 物理 SRAM | 40 × RAMTP1024X16，80 KiB |
| SRAM 库面积 | 710,313.75 µm² |
| 总单元面积（含 SRAM） | 965,371.79 µm² = 0.9654 mm² |
| 2.25 mm² 单元面积预算 | PASS，剩余约 57.1% |
| TT setup WNS | +0.049 ns，PASS |
| TT hold WNS | −1.04846 ns，FAIL |
| 综合/报告执行 | COMPLETE |

这是 TT 1.1V / 25℃、6.667 ns 周期的综合结果，不是最差角或布局布线签核。
宏面积与时序已接入真实 DB，且检查确认存在经过宏读输出的受约束路径。
当前 hold 违例不能从 COMPLETE 或 setup PASS 中忽略。

现有脚本使用 `set_clock_uncertainty 1.0`，没有分别指定 setup / hold；
该设置同时给 hold 加入 1 ns 裕量。需要结合最差 `timing_min.rpt` 中的时钟不确定性、
库 hold requirement、起终点和实际最小数据延迟分解原因，再决定正确的约束与修复。
目前保留原约束与报告，不通过减小裕量、false path 或多周期约束消除告警。
即使仅作数值分解、假设整整 1 ns 均来自该裕量，剩余仍约为 −0.04846 ns，
不能据此宣布真实 hold 已满足。

### 最差 hold 路径已确认

服务器路径报告显示 `g_shared_kv.u_kv` 的 `committed_data_reg[*]` 到真实
`RAMTP1024X16/DB[*]`。数据经寄存器和两个组合单元约 0.25 ns 到达；
宏库 hold 要求约 0.30 ns，hold uncertainty 为 1.00 ns，因此需求约 1.30 ns、
slack 约 −1.05 ns，与汇总 −1.04846 ns 一致。
同一报告的理想时钟网络延迟为 0。即使只在数学上分离 1 ns 裕量，仍有约 48 ps 缺口。

本轮先保持已记录的 setup/hold 各 1 ns 不确定性、6.667 ns 周期及 I/O 约束，
从已综合检查点执行 `set_fix_hold [get_clocks clk]` 与
`compile -incremental_mapping -only_hold_time`。此选项属于普通 `compile`，
不传给 `compile_ultra`；参见 [Synopsys Design Compiler 用户手册](https://studylib.net/doc/27833944/design-compiler-user-guide)。
这是当前 TT、理想时钟模型下的增量 hold 修复，物理时钟树与布线后仍需复核。

已上传小包 `kwt_hold_fix_20261029.tar.gz`，入口为：

```bash
mkdir -p ~/soc/kwt_hold_fix_20261029
tar -xzf ~/Desktop/kwt_hold_fix_20261029.tar.gz -C ~/soc/kwt_hold_fix_20261029
bash ~/soc/kwt_hold_fix_20261029/tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261029_150543_tqH6Fc --fix-hold
```

入口要求有已验证输入的映射检查点，不回退到重新跑 RTL 全综合。复用现有三套
真实宏功能回归和 SRAM DB，保持原始源码、原检查点和原报告不变。
新结果保存在 `hold_repair_<时间>_<随机>/` 中。

- `hold_before.rpt` / `setup_before_hold.rpt`：优化前路径。
- `hold_before.sdc` / `hold_after.sdc`：前后约束；脚本对时钟、I/O 和路径约束做一致性检查。
- `kwt_encoder_12_hold_attempt.ddc`：即使后续检查失败也保存本次优化结果。
- `timing_min.rpt` / `timing_max.rpt`：优化后路径，精度提高到小数点后 6 位。
- `HOLD_REPAIR_STATUS`：仅当面积、setup、hold 均 PASS 时才为 PASS。

本地已验证脚本的检查点选择、约束不变检查与失败状态传递（使用模拟 EDA 命令）。
服务器实际 v4 修复运行已在 4 小时上限处被 `timeout` 发送 SIGTERM 终止，
没有完成优化及最终报告，**不能判定 hold 闭合**。
修复目录为 `hold_repair_20261029_210857_nk61CC`（以服务器实际路径为准）。
最后进度约为 3:59:17，面积栏为 1,137,205.5 µm²；这是优化中的数值，
不能替代完成后的面积、setup、hold 报告。该运行的中间内存状态未保存为检查点，
不能靠再次执行原命令接着上次的四小时继续优化。

### 超时后：先做有界的约束诊断

不再直接重跑四小时全设计 hold 修复。新增 `--audit-hold` 入口，仅从原始
已验证的综合检查点读入真实库和映射网表；不执行 compile、插缓冲或导出新网表。
本地赛题摘要规定 150 MHz，但未找到 hold uncertainty 必须为 1 ns 的依据；
该数值目前来自工程综合脚本，仍需结合正式评测约束、PLL/时钟树预算核定。
Synopsys 允许分别设置 setup 与 hold uncertainty，参见
[Timing Constraints and Optimization User Guide](https://studylib.net/doc/28481429/synopsys%C2%AE-timing-constraints-and-optimization-user-guide)。

诊断先按完整原约束输出全局、SRAM 输入和其他寄存器输入的最差 hold 路径，
然后只在当前 DC 进程内将 hold uncertainty 设为 0 作敏感性对照；setup 及 I/O
约束保留，检查 setup WNS 不变。**零裕量对照不是新的合格标准，也不意味着
真实 hold 满足要求**。不改 `dc_compact.tcl` 的生产约束、不覆盖原 DDC 或报告。

```bash
mkdir -p ~/soc/kwt_hold_audit_20261030
tar -xzf ~/Desktop/kwt_hold_audit_20261030.tar.gz -C ~/soc/kwt_hold_audit_20261030
bash ~/soc/kwt_hold_audit_20261030/tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261029_150543_tqH6Fc --audit-hold
```

仅诊断的总工具运行上限为 900 秒，日志实时显示并保存在新的 `hold_audit_*`
目录；不会重新跑 VCS 或转换库。输出 `AUDIT_BASELINE_*` 为原约束下的结果，
`AUDIT_ZERO_HOLD_UNCERTAINTY_*` 仅为诊断对照。`AUDIT_ACCEPTANCE: NONE` 明确
表示本次不作时序通过判定，最终状态仍取原约束报告，hold 尚未闭合。

### 43 秒真实库诊断结果（2026-10-30）

服务器 `hold_audit_20261030_123348_0F3TpU`（以实际目录为准）成功完成，
总用时 43 秒，且原检查点 SHA256 未变化。结果如下，单位 ns：

| 检查 | 原约束（hold 裕量 1 ns） | 诊断对照（hold 裕量 0 ns） |
|---|---:|---:|
| 全局 setup WNS | +0.0487933 | +0.0487933 |
| 全局 hold WNS | −1.04846 | −0.0484576 |
| SRAM 输入 hold WNS | −1.04846 | −0.0484576 |
| 非 SRAM 寄存器输入 hold WNS | −0.900744 | +0.0992561 |

这确认了普通寄存器的大量违例主要受 1 ns 裕量驱动；在零裕量、TT、理想
时钟对照下，SRAM 输入仍有约 48.46 ps 真实最小延迟缺口。零裕量不是新的
合格标准，原约束下的 hold FAIL 继续保留。

正式赛题文本 `doc/赛题指南_文本.txt` 规定 150 MHz、不包含布局布线，
要求完整有效的时序约束及报告，但未指定 hold uncertainty 的数值。
当前尚无组委会 PLL/时钟树的已核定 hold 预算，不能把某个试验值称为官方要求。

下一步使用**显式标记的预算试验**：setup 保留原 1 ns，hold 暂取 0.10 ns。
100 ps 是工程假设，既不是签核值，也不是依据当前负 slack 反推的通过阈值。
在原网表上该试验预计仍有 SRAM hold 约 −0.14846 ns、寄存器 hold 约
−0.000744 ns，因此仍需实际插入延迟并重新检查 setup/hold 和面积。

```bash
mkdir -p ~/soc/kwt_hold_pilot_20261030
tar -xzf ~/Desktop/kwt_hold_pilot_20261030.tar.gz -C ~/soc/kwt_hold_pilot_20261030
bash ~/soc/kwt_hold_pilot_20261030/tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261029_150543_tqH6Fc --pilot-hold 0.10
```

试验从原始已验证的综合检查点开始；不复用超时优化的内存状态。
新结果存入 `hold_pilot_*`，保留原约束 SDC、原始 hold 报告、原始 slack 与状态。
输入检查点在前后进行 SHA256 验证；不覆盖原 run 或正式综合约束。
修复前后比较试验 SDC 的时钟、IO 及路径预算，优化不得进一步放宽试验约束。
工具限时 1,200 秒，超时发 TERM，最多再给 30 秒退出宽限；实时显示日志。

只有试验的面积、setup、hold 全部通过时，才输出
`PILOT_HOLD_REPAIR_STATUS: PASS`；不会输出正式的 `HOLD_REPAIR_STATUS: PASS`。
`ORIGINAL_BUDGET_CLOSURE: NOT_ESTABLISHED` 始终保留。
即使试验成功，也仍需核定最终时钟预算、工艺角并验证修复网表功能，才能冻结提交。

### 100 ps 预算试验的实际结果（2026-10-30）

本轮工具执行结束并生成报告，未超时，但 `PILOT_HOLD_REPAIR_STATUS: FAIL`：

| 项目 | 试验结果 |
|---|---:|
| 含 SRAM 总单元面积 | 978,790.64 µm²（0.9788 mm²），预算内 |
| setup WNS | +0.049 ns |
| hold WNS | −0.100 ns，仍有违例 |

这些数值属于 hold uncertainty = 0.10 ns 的试验网表，不替代原约束基线。
需要检查优化后 `timing_min.rpt` 的起点、终点、时钟及库要求，才能定位残留
违例；仅凭恰好 −0.100 ns 不能判定是 SRAM 数据、时钟或 IO 路径问题。
当前不减小试验裕量，也不添加 false path；先读取已有报告，无需再跑优化：

```bash
sed -n '1,100p' ~/soc/kwt_sram_20261029_150543_*/hold_pilot_*/dc_out_bound/timing_min.rpt
```

读取本轮最差 hold 路径（只读，不需重跑综合）：

```bash
sed -n '1,100p' ~/soc/kwt_sram_20261029_150543_*/synth_recovery_20261029_154753_*/dc_out_bound/timing_min.rpt
```

## 已通过功能验证后的综合恢复

修复包 `kwt_sram_dc_fix_20261029.tar.gz` 仅含修正后的 DC 脚本、恢复入口和本文档。
无需重新解包 RTL、重新跑 VCS 或转换 SRAM 库：

```bash
mkdir -p ~/soc/kwt_sram_dc_fix_20261029
tar -xzf ~/Desktop/kwt_sram_dc_fix_20261029.tar.gz -C ~/soc/kwt_sram_dc_fix_20261029
bash ~/soc/kwt_sram_dc_fix_20261029/tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261029_150543_tqH6Fc
```

恢复入口要求原 run 的三套真实宏测试及库转换记录全部 PASS，并重新验证源码、
向量和 Liberty 的 SHA256。任何记录缺失或输入变化都停止；不把旧 PASS 用于新 RTL。
新日志/报告保存在原 run 下新建的 `synth_recovery_<时间>_<随机>/`，不覆盖原日志。

DC 仅对内置常量引用 `**logic_0**` / `**logic_1**` 豁免 Liberty leaf 检查。
普通标准单元和 SRAM 仍必须存在于真实库，缺失模块、GTECH、其他未知 pseudo-cell
仍会失败。真实宏数必须为 40，宏面积和受约束 SRAM 读路径检查继续保留。

v2 在检查前未保存 DDC，所以首次恢复仍需重新综合（原 run 约 10 分钟）。
新脚本在 `compile_ultra` 后、检查与报告前保存 `_compiled.ddc` / `_compiled.sdc`；
后续恢复可复用同一组已验证输入的检查点，复查时钟与宏数量后继续报告。
恢复脚本记录输入摘要，拒绝使用输入不匹配的恢复检查点。

## 实际宏回归与综合运行包

当前包名 `kwt_sram_binding_20261029_v2.tar.gz`，包含本工程 RTL、检查后的引脚配置、
三套 testbench、十二层向量及运行脚本。**不包含或重新分发工艺库/宏模型**；
脚本从服务器现有库位置复制宏 Verilog 到本次运行目录。

```bash
mkdir -p ~/soc/kwt_sram_binding_20261029_v2
tar -xzf ~/Desktop/kwt_sram_binding_20261029_v2.tar.gz -C ~/soc/kwt_sram_binding_20261029_v2
bash ~/soc/kwt_sram_binding_20261029_v2/tools/run_kwt_sram_binding.sh --synth
```

运行流程：

1. 校验包内 SHA256 清单，在 `~/soc/kwt_sram_<时间>_<随机>/` 创建隔离快照。
2. 用官方 `RAMTP128X16.v` / `RAMTP1024X16.v` 依次验证适配层、打包层和十二层编码器。
3. RTL 功能仿真关闭 specify timing checks，保留模型内部传播延迟、保持模式和
   碰撞检查；**不定义 `ARM_UD_MODEL`，不以自编模型替换官方模型**。
   这种无 SDF 的理想 RTL 仿真不判断物理 setup/hold。
4. 三套测试均有明确 PASS 标记，十二层还必须满足 6,336 输出和 3,232,909 拍，
   才继续生成 TT 1.1V/25C 的私有 DB。
5. 优先 `lc_shell` 转换；没有该命令时尝试 `dc_shell` 的库编译能力（仍需对应许可）。
   失败就停止并打印日志，不使用黑盒或旧文件降级。
6. DC 要求 40 个真实宏、所有 leaf 已解析、真实宏面积为正及存在 SRAM 读时序路径。
   输出包含 SRAM 的面积、TT setup/hold slack 和各项状态。

只跑基础存储测试可加 `--suite unit`，不能同时要求 `--synth`。
默认完整回归使用 VCS；编译超时 900 秒、每套仿真超时 3,600 秒，综合超时 14,400 秒。
脚本打印每个阶段的 RUN / PASS。编译失败时打印第一条诊断及上下文，
仿真失败时打印日志尾部，保留完整日志和工作目录，
编译器或 `$finish` 返回 0 也不能代替 testbench 的 PASS。

工作目录包含 `runner.log`、`results.tsv`、`logs/`、源码/向量/Liberty 的 SHA256。
宏模型和原 CPU 平台均不被修改，已有 CPU 回归工作目录不受影响。
`RESULT: COMPLETE` 仅表示请求的工具执行完毕；面积、setup、hold 状态单独报告，
不把综合成功等同于时序达标，也不等同于最差角和布局布线签核。

### 首轮服务器编译失败与 v2 修正

首轮工作目录 `kwt_sram_20261029_145335_HAAZuN` 停在
`compile_tb_kwt_foundry_sram16`：`Error-[UPIMI-E] Undefined port in module instantiation`。
128、1024 两个模型的当前生效模块接口均没有 `VDDCE/VDDPE/VSSE`。
第一次清单工具按原始文本扫描，将未启用分支的电源端口也列出来；
运行脚本据此无条件启用适配层电源端口，造成不匹配。

v2 去掉运行脚本中的 `+define+KWT_SRAM_POWER_PINS`，匹配当前默认模型分支。
不修改官方模型，不改变 EMA、retention、collision 配置及存储时序结构。
同时保存每个测试的 `compile_command.sh`，并在失败时优先显示第一条报错，
避免 `MAX_ERROR_COUNT` 尾部信息掩盖根因。原失败日志继续保留。
v2 已经服务器真实模型回归确认通过，结果见上方；当前待完成的是最终综合报告。

## 服务器只读检查

本地工具 `tools/inspect_kwt_sram.py` 兼容 Python 2.7 / 3。
扫描 `/storage1/admin_public_dir/SRAM_Lib_2025`，列出指定深度、16-bit 宏的真实
模块端口，以及 `.lib` / `.db` / `.lef` / 压缩包路径。工具只读库文件，
仅创建指定的 JSON 报告；不会解压、修改平台或执行综合。

上传包：`kwt_sram_probe_20261029.tar.gz`，落在服务器 `~/Desktop/`。

```bash
mkdir -p ~/soc/sram_binding_tools_20261029
tar -xzf ~/Desktop/kwt_sram_probe_20261029.tar.gz -C ~/soc/sram_binding_tools_20261029
python ~/soc/sram_binding_tools_20261029/inspect_kwt_sram.py --out ~/soc/kwt_sram_inventory_20261029.json | tee ~/soc/kwt_sram_inventory_20261029.txt
```

若提示根目录不存在或只有压缩包，先依据输出确认库所在位置；工具支持
`--root /实际目录`（可重复）。如果需要查看某个宏的行为与 timing checks：

```bash
python ~/soc/sram_binding_tools_20261029/inspect_kwt_sram.py --details RAMTP1024X16 --out ~/soc/kwt_sram_inventory_20261029.json
```

其中 `RAMTP1024X16` 必须替换为首次检查输出的实际模块名。

## 控制脚与双端口库的聚焦检查

第一次清单扫描混入了模型内部 task/function 的局部形参，不能把那些形参当成
宏端口。宏主模块的实际端口为 `QA/CLKA/CENA/AA/CLKB/CENB/WENB/AB/DB/EMAA/EMAB/RET1N/COLLDISN`，
模型另有电源端口。`WENB` 是 16-bit，但有效电平与固定工作值需由正文/手册核对。

后续包 `kwt_sram_controls_20261029.tar.gz` 已上传；仅含只读检查工具，不含待核对的生产配置：

```bash
mkdir -p ~/soc/sram_controls_20261029
tar -xzf ~/Desktop/kwt_sram_controls_20261029.tar.gz -C ~/soc/sram_controls_20261029
python ~/soc/sram_controls_20261029/inspect_kwt_sram_controls.py
```

该工具只打印两个双端口宏的关键控制语句、TT 库名称/电压/面积和文档路径；
若服务器有 `pdftotext`，还会读取手册的相关段落。完整正文保存在
`~/soc/kwt_sram_controls_20261029.txt`，方便后续定位，不上传或修改共享库。

## 接线与验证要求

结构已实现；得到实际控制信息后补全 `kwt_sram_pins.vh` 并验证，不推测有效电平：

1. 确认读/写端口、时钟边沿、地址及数据位宽、CEN/WEN/写掩码极性和测试脚固定值。
2. 确认读延迟是一拍；实际模型同址读写即使输出 X，也不能破坏打包层 forwarding。
3. ASIC 综合读取匹配工艺角的宏 DB；宏只放入 link library，避免自动映射成错误存储。
   没有 DB、宏未 link 或位宽不匹配时应报错，不能继续产生“达标”摘要。
4. 先用实际宏 Verilog 模型运行三种深度的 `tb_kwt_packed_sram`（若库含相应规格），
   检查连续 nibble/byte 更新、同址转发、A/B/A 地址交替、零掩码和复位后数据保持。
5. 再运行编码器功能回归并比对逐位输出及周期，随后重新综合；报告中确认默认配置
   40 个物理 `RAMTP1024X16`，未解析引用为零，宏面积非零，宏时序路径被分析。

功能模型通过不代表时序签核。150 MHz 仍需带真实宏时序模型的分析；功耗还需活动数据。
