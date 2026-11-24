# LayerNorm 时序与四路 Softmax

2026-10-27。本轮承接文档 15 的共享 64-MAC、合并 K/V 架构。

## 1. 问题定位

用户提供的 150 MHz 综合报告中，WNS 为 -14.376 ns，最差路径从
`u_ln/col_reg` 到 `u_ln/out_data_reg`：20.906 ns、31 级逻辑。
Newton 四阶段控制已经拆开，但输出计算仍把存储读取、减均值、乘 inv、
乘 gamma、加 beta、饱和串在一个周期中。

不能把每次乘法都写到不同 FSM 状态就认定时序达标：单次宽乘法也可能形成
多个 DSP 的组合级联。需要以相同 6.667 ns 约束下的新报告为准。

## 2. 输出流水

新增 `kwt_mul_pipe`，用 16-bit 分块乘积、对角线归并和分段进位实现
六级流水，吞吐为每拍一次，保留有符号乘积低 64 位的原始语义。
LayerNorm 输出采用读数据、减均值、归一化乘法、gamma 乘法、加 beta、饱和流水；
地址、gamma、beta、末元素标志与 valid 同步传递。行末等待最后一个结果写回后再换行。

N=64 时，均值仍在 int16 范围内，所以差值只需 17 位；归一化乘积右移后
需 41 位，再乘 int16 gamma 需 57 位。该缩位不改变结果。
其他 N 保留原先宽位运算语义。均值、方差、Newton 的原有截断和溢出约定保留。

后续分模块报告进一步发现方差路径约 14.2 ns、Newton 路径约 11.9 ns，
因此还把四路统计拆成读、减均值、平方、两层归并和累加；Newton 三次依赖乘法
复用一套流水乘法器并逐次等待 valid。仍执行三次迭代，保留每一步的低 64 位截断。

其他长路径也同步调整：参数 SRAM 返回、bias 相加、requant 乘法、舍入、饱和、
GELU 分级寄存；MAC 输入、乘积、加法树和反馈累加分级寄存，首段标志随数据
传递到累加器；残差对齐分为输入捕获、双乘法、带舍入求和、饱和，最后写入 LN 后才启动。
这些变化提高单级可承受的时钟频率，也增加了每个算子收尾时的排空周期。

## 3. 四路 Softmax

`SOFTMAX_LANES=4` 为默认值；设成 1 可运行同一架构的串行对照。
不是同时处理四行，而是在一行中每拍处理四个元素：

- score 与 exp 按元素下标低两位分为四个 bank。
- 最大值、exp LUT 与求和均分级寄存；四路乘法后完成概率舍入。
- 保留一套 27 拍串行除法器，使用相同 LUT、整数倒数及概率舍入。
- 输出为四个字节加四位 mask；99 元素最后一组只写三个有效字节。

最终采用相同全部流水配置，串行版与四路版整层对照：

| 指标 | 串行 Softmax | 四路 Softmax |
|---|---:|---:|
| 单行 Softmax 本体 | 328 拍 | 117 拍 |
| score + Softmax 阶段 | 74,646 拍 | 53,757 拍 |
| 单层周期 | 274,032 拍 | 253,143 拍 |
| 有效 MAC 利用率 | 34.899% | 37.779% |

每层减少 20,889 拍，占串行对照的 7.62%。两者 MAC 发射数都为 98,604，
有效 MAC 数都为 6,120,576，6,336 个输出逐位一致。
仅拆 LN 输出时的中间版本，串行/四路为 246,708 / 225,819 拍，节省 8.47%；
该版本 WNS 仍为 -10.650 ns，不能用它代表最终时序流水版。
文档 15 中 241,956 拍的旧结果采用先前流水配置，也不能把全部差值都归因于 Softmax。
本轮最终单层周期比旧 V2 增加约 4.62%，因此不能声称“整体周期减少 9%”。
时序能否运行到目标频率与仿真周期数必须同时评估。

十二层（包含本地参数扫描及层间搬运）为 3,232,909 拍，有效 MAC 利用率
35.498%；6,336 个输出逐位一致。按 150 MHz 换算为 21.553 ms，
这是周期换算值，实际平台总线等待和 ASIC 布局布线尚未计入。

`KV_SHARED=0` 的宽 K/V 备选在当前全部流水及四路 Softmax 下也已逐位通过：
单层 185,427 拍、有效 MAC 利用率 51.575%，连续发射没有触发量化队列溢出。
其 K/V 仍需 64 个小宏，默认窄版仅需 8 个；此处只报告更新后的仿真周期，
不沿用文档 15 的旧综合面积或时序数字。窄版的注意力读带宽仍是后续优化方向。

## 4. FPGA 综合资源与时序

相同 Artix-7 器件、6.667 ns 时钟与 2 ns 输入/输出延迟下：

| 最终流水配置 | LUT | FF | DSP | RAMB36 | RAMB18 |
|---|---:|---:|---:|---:|---:|
| 串行 Softmax | 16,771 | 17,674 | 27 | 2 | 43 |
| 四路 Softmax | 17,069 | 18,083 | 29 | 2 | 43 |

四路版代价为 +298 LUT、+409 FF、+2 DSP，BRAM 数不变。
串行 Softmax 的宽乘法本身仍有时序违例（整体 WNS -5.642 ns）；
该配置用作数值、周期及资源对照，不能认为它也达到了 150 MHz。

四路版保留 FPGA I/O buffer 的完整报告中 WNS 为 -1.924 ns，
最差路径为 `u_enc/out_we_reg -> out_we`，主要包含 OBUF 延迟。
同一份综合网表的寄存器间最差 slack 为 **+0.712 ns**，输入到寄存器为
**+3.007 ns**。原先的 20.906 ns LN 输出计算链已消除；
不能把内部时序通过等同于整个 FPGA 引脚接口已经通过。

完整报告：`syn/compact_out/timing.rpt`；内部路径：`timing_core.rpt`；
输入路径：`timing_input.rpt`；输出路径：`timing_output.rpt`。
本轮迭代报告分别保存在 `compact_ln_pipe`、`compact_requant_pipe`、`compact_datapath_pipe`。

`-ooc` 另外执行 out-of-context 模块综合，不插入 FPGA 引脚 I/O buffer；
时钟、输入/输出延迟及负载约束均沿用原 XDC，报告写入 `compact_out_ooc`。
它反映嵌入 SoC 的 encoder 模块边界，不替代 FPGA 带引脚报告或 ASIC 签核。
该模式实测 setup WNS **+0.817 ns**、hold 最差 **+0.165 ns**，违例端点均为 0。
资源为 16,931 LUT、18,083 FF、29 DSP、2 RAMB36 + 43 RAMB18。
相同数据路径在带引脚与模块模式下都是 5.818 ns，slack 差异来自时钟与边界建模。
时序覆盖检查中，无时钟寄存器、未约束内部端点、缺失输入/输出延迟、组合环均为 0。

## 5. 可复现检查

在项目根目录执行：

```powershell
./sim/run_nonlinear.ps1
./sim/run_compact.ps1 -CompareSoftmax -IncludeTop
& D:/Xilinx/Vivado/2022.2/bin/vivado.bat -mode batch -source syn/run_compact.tcl
& D:/Xilinx/Vivado/2022.2/bin/vivado.bat -mode batch -source syn/run_compact.tcl -tclargs -ooc
```

串行 Softmax 综合对照加 `-tclargs -serial-softmax`，报告输出到
`syn/compact_out_sm1`；默认四路报告位于 `syn/compact_out`。
本轮开始前的用户时序报告保存在 `syn/compact_pre_ln_out`。

局部回归覆盖：四种乘法位宽的随机/边界/valid 空拍/复位；
60×99 个 Softmax 黄金值；1,280 个 LayerNorm 黄金值；
相对修改前 LayerNorm 的 3,072 个极值及随机输出，含方差溢出、不同 eps、重复启动。
另有 MAC、requant/GELU、残差对齐的随机/边界/连续发射/空拍/复位测试。

最终整机 MFCC → 分类回归 **3/3 通过**，预测分别为 1、1、11，与黄金值一致。
首帧为 3,247,169 拍（按 150 MHz 换算 21.648 ms）；日志为
`sim/compact_v2_top_snap.log`。整层、十二层及整机运行的统一脚本最后报告
`All compact checks passed.`；局部脚本报告 `All nonlinear checks passed.`。

综合结果是 Artix-7 原型检查；比赛工艺的面积与时序仍需指定标准单元及 SRAM 宏库验证。
