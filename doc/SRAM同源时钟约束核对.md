# RAMTP1024X16 同源时钟核对与半拍候选

日期：2026-10-30。本文供核对宏接口和 STA 约束使用，未发送给任何外部人员。

手册已提取：同一行碰撞开启检测时不保证写入，原同沿连接不能以数据 forwarding
为依据验收。当前 RTL 已改为半拍版，v8b 真实宏回归和新综合已完成；宏时钟及
写入路径摘要为正，原 1 ns hold 基线为 −0.903385 ns。v9 在 100 ps hold
试验中修复后通过：面积 0.9812 mm²、setup +0.047 ns、hold +0.000272155 ns；
最终时钟预算待确认。细节及新验证入口见
[SRAM 半拍适配验证](SRAM半拍适配验证.md)。下文同沿连接及 PPA 记录均为历史证据。

## 原同沿方案需要核对的问题

我们使用竞赛提供的 `RAMTP1024X16`，A 口同步读、B 口同步写，两个时钟引脚
`CLKA/CLKB` 均直接连接同一个 150 MHz 上升沿时钟。固定配置为
`EMAA=EMAB=3'd2`、`RET1N=1`、`COLLDISN=1`，保留模型碰撞检查。
读写地址独立，连续局部写使用读改写和同址 forwarding。

依据宏交付包的 `datasheet/`、模型与 Liberty 核对：

1. 宏是否支持这种同源、同相、同边沿的 1R1W 用法？同址及同 row 不同 column
   读写分别有何限制，如何保持模型碰撞检查的有效性？
2. 如支持，Liberty 的 `CLKA -> CLKB`、`CLKB -> CLKA` `hold_rising` 检查在此
   用法下应如何进行 STA 建模？请提供推荐 SDC 或应用说明，区分时钟对之间的
   相关性与普通寄存器到 SRAM 数据路径所需的 hold 裕量。
3. 两个方向的 `setup_rising` 检查与模型中的 `ARM_MEM_COLLISION` 窗口如何解释？
   若需要错相时钟，请提供合法边沿关系和最小间隔，供 RTL 时序契约复核。
4. 明确自编 SDC 的 setup/hold uncertainty、工艺角和输入/输出预算的工程依据。
   赛题要求参赛队提交 SDC，不提供官方 SDC；当前正式目标为 150 MHz，
   100 ps hold 裕量仍为未冻结的试验假设。

## 已取得的证据

真实宏 RTL 功能回归已通过：适配层、打包层以及十二层编码器的 6,336 个输出
逐位一致。该回归关闭 specify timing checks，保留模型内部传播延迟和碰撞检测，
因此不能替代宏用法及物理时序约束的确认。

真实库综合使用 TT 1.1 V / 25℃、周期 6.667 ns。原始全局 1 ns uncertainty
基线的 hold WNS 为 −1.04846 ns，其 FAIL 结论保留。
另一次试验仅把 hold uncertainty 设为 0.100 ns、setup 保持 1 ns，然后实际
插入延迟修复。试验含 SRAM 的总单元面积为 978,790.64 µm²。

只读审计修复后的试验网表，且所有 timing arc 和 SDC 命令均保留，得到：

| 项目 | 试验 slack / ns |
|---|---:|
| 全局 setup | +0.0487933 |
| SRAM 非时钟输入 hold | +0.000272155 |
| 其他寄存器数据输入 hold | +0.0248893 |
| 数据终点集合 hold | +0.000272155 |
| 经过 SRAM 读输出的 hold | +0.373557 |
| SRAM 时钟引脚终点 hold | −0.100000 |

最差时钟路径为 `clk -> RAMTP1024X16/CLKA` 相对于 `CLKB` 的检查，另有
反向路径。两者使用同一理想时钟网络：到达时间为 0，library hold time 为 0，
uncertainty 为 0.100 ns，故 slack 为 −0.100 ns。

Liberty 原文 `time_unit` 为 1 ns。两个时钟方向的 `hold_rising` 约束表全部为 0。
在当前 EMA=2 的条件下，库还存在非零 `setup_rising` 表：

| 方向 | 当前 EMA 条件下的 when | setup 表最小/最大值（ns） |
|---|---|---|
| CLKB → CLKA | RET1N & !EMAA[2] & EMAA[1] & !EMAA[0] & !CENA | 0.606164 / 0.975897 |
| CLKA → CLKB | RET1N & !EMAB[2] & EMAB[1] & !EMAB[0] & !CENB | 0.743684 / 1.1342 |

官方模型的原始跨时钟 `$setuphold` 摘录使用 `ARM_MEM_COLLISION` 作为 setup
参数，hold 参数为 0。提取工具未执行模型预处理，原始语句不能单独证明其
激活条件或同步连接的合法性；需要结合完整模型和宏应用说明解释。

用户已确认宏资料目录为
`/storage1/admin_public_dir/SRAM_Lib_2025/RAMTP1024X16/datasheet/`。
此前检查仅查找 PDF，未覆盖其他格式，不能把该结果当作资料不存在。
读取入口已确认目录中有 28 个文件，已选中的两份为 PostScript 数据手册；当前 TT 文件为
`RAMTP1024X16_tt_1p10v_1p10v_25c.ps`。首次读取因 v1 不支持该格式而未取得正文。
v2 已补充 Ghostscript / ps2ascii / ps2pdf 转换，保留全文、路径和 SHA256；
服务器 v2 已返回正文：两个端口都在各自时钟上升沿锁存，开启检测时同一行
碰撞不保证写入，部分读取也不受支持。原同沿方案的安全性未建立。

独立维护的 [kwt_encoder_12.sdc](../syn/kwt_encoder_12.sdc) 已建立，完整复现当前
1 ns setup/hold 基线，综合入口读取此文件。该 SDC 是可复现的工程约束源，
保留原 1 ns setup/hold 预算，供新半拍 RTL 独立评估；最终提交预算尚未冻结。

## 当前工程结论

100 ps 试验预算下，已检查的数据 hold 路径通过，最小余量约 0.272 ps。
这是相对试验预算的综合余量，不是跨工艺角或最终时钟预算的结论。
整体 hold 仍为 FAIL；不能根据“同一时钟”直接删除库检查或宣布时序闭合。
当前已根据手册改变宏连接方式：A 上升沿读、锁存完整写事务、B 下降沿写。
本地接口测试及服务器真实宏开启时序检查的短测试、完整功能回归均已通过。
本轮新综合面积 970166.81 µm²、setup +0.047 ns，全局 hold −0.903385 ns。
本轮最差 hold 已定位：`q_group_reg[0]` → 参数 SRAM 的 `AA[2]`，相对 `CLKA`。
到达 0.264810 ns，库 hold 0.168195 ns，1 ns 裕量下 slack 为 −0.903385 ns。
有界 100 ps 试验已通过，见 [半拍保持时间试验](SRAM半拍保持时间试验.md)；原基线仍为 FAIL。
不继续重复原全局修复，不把试验结果替代原约束基线，也不修改官方库。

服务器证据位于原 run `~/soc/kwt_sram_20261029_150543_tqH6Fc/` 下：

- `hold_pilot_*/dc_out_bound/`：修复后的试验 DDC、SDC、网表及全局时序报告。
- `hold_clock_audit_*/summary.txt`：分类 slack 与原库、模型摘录。
- `hold_clock_audit_*/dc_out_bound/`：数据输入、读输出、时钟终点的独立路径报告。
- `hold_clock_audit_*/sram_clock_arc_evidence.txt`：原始摘录路径及 SHA256。

本地未复制工艺库或宏模型。新候选必须从新 RTL 重新综合和回归，不能复用
旧同沿网表的 PASS 或 PPA。独立 SDC 不删除任何宏时序检查。
