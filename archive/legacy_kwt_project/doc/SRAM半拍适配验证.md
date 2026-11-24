# SRAM 半拍适配候选（2026-10-30）

当前 RTL 已改为 A 口在根时钟上升沿读、B 口在根时钟下降沿写。
v8b 已取得本轮真实宏回归和新鲜综合结果；原 1 ns hold 基线仍未闭合。
随后 v9 在 100 ps hold 裕量试验中完成实际延迟修复，面积 0.9812 mm²、
TT setup +0.047 ns、hold +0.000272155 ns，试验通过。最终时钟预算仍待确认。
本轮结果独立于旧连接方式的 PASS 或 PPA。

## 服务器 v8b 实测结果

用户于 2026-10-30 返回完整运行摘要截图。隔离工作目录为
`~/soc/kwt_sram_20261030_161124_*/`，完整日志在 `runner.log` 和 `logs/`。

- 开启 specify 检查的 150 MHz 半拍测试：128/1024/4096 深度及半拍中复位均通过。
- 适配层和打包层全部深度通过；真实宏十二层编码器 6336 个值逐位一致。
- 编码器周期仍为 3232909，未增加逻辑周期；MAC issues 为 1183248。
- 40 个 RAMTP1024X16、80 KiB；综合由本轮新 RTL 完成，没有全局 hold 修复。

| 项目 | 本轮结果 |
|---|---:|
| SRAM 库单元面积 | 710313.75 µm² |
| 含 SRAM 总单元面积 | 970166.81 µm²（0.9702 mm²） |
| 面积预算 | PASS（2250000 µm²） |
| 全局 setup WNS | +0.047 ns（摘要舍入） |
| 全局 hold WNS | −0.903385 ns，FAIL |
| 宏时钟 max 路径 slack | +1.00224 ns |
| 写入 max 路径 slack | +1.46429 ns |
| 宏时钟 min 路径 slack | +2.3335 ns |
| 写入 min 路径 slack | +2.21915 ns |

时钟/写入的 max、min 分别对应 setup、hold 检查摘要。独立 SDC 仍为
setup/hold 各 1 ns。摘要支持宏时钟及写入路径在本轮分析中通过；仍须查看
完整路径的边沿关系。随后取得的 `timing_min.rpt` 第一条路径为
`g_compact.u_enc/q_group_reg[0]` → 参数 SRAM 的读地址 `AA[2]`，相对 `CLKA`
检查 hold。数据到达 0.264810 ns，库 hold 为 0.168195 ns，uncertainty 为
1.000000 ns，故 slack = 0.264810 − 0.168195 − 1 = −0.903385 ns。
这是读地址路径；摘要中写入路径通过不意味着所有 SRAM 输入都通过。
有界试验已通过，结果见 [半拍保持时间试验](SRAM半拍保持时间试验.md)。原 1 ns
基线 FAIL 继续保留，本次半拍版试验与此前旧同沿版试验分别记录。

## 手册依据

服务器已成功用 Ghostscript 读取
`RAMTP1024X16/datasheet/RAMTP1024X16_tt_1p10v_1p10v_25c.ps`。
提取全文在 `~/soc/kwt_sram_datasheets_20261030_153218_*/RAMTP1024X16_*.txt`。

- L25：A、B 分别在 CLKA、CLKB 上升沿锁存读、写事务。
- L46：开启碰撞检测时，读写行地址相同的碰撞不能保证写入；关闭检测时，读数据不确定。
- L52：碰撞中通过 WENB 实现部分读取不受支持，且不取决于 COLLDISN。
- 当前 EMA=2 的时钟间隔表摘录：A→B 约 0.790 ns，B→A 约 0.929 ns。
  具体条件和单位须与全文表头一起保存。不能把摘录单个值当成所有角的上限。
- 原始 Verilog 默认 `ARM_MEM_COLLISION=3.000 ns`，也必须保留并运行检查。

这些信息不足以支持原来的同沿连接；仅在打包层转发读数据也不能保护一次
不保证成功的物理写操作。`COLLDISN=1`、EMAA/B=2、RET1N=1 保持。

## 接口和时钟

`kwt_foundry_sram16` 在根上升沿锁存完整的 `we/wa/wd`，B 口用实际反相时钟
`~clk` 写入锁存值。4096 深度的写 bank 也由锁存后的地址选择。
逻辑读操作仍返回本次逻辑写之前的数据，本次写在下一次逻辑读之前完成。
打包 SRAM 的 RMW 和 forwarding 不增加逻辑周期。

```text
root clk       ↑ n             ↓ n+0.5          ↑ n+1
A read         读旧值                           可见本次写
write staging  锁存 we/wa/wd
B write                        提交锁存事务
```

6.667 ns、50% 占空比时，两个方向间隔均约 3.3335 ns；真实时钟偏斜、占空比
误差和各路径余量仍需检查。物理实现必须保持反相关系，不能给两个引脚分配
无关时钟。简单反相的时钟极性由 STA 沿实际网表传播，候选不使用时序例外。
相关工具语义见 Synopsys《Timing Constraints and Optimization User Guide》
U-2022.12 的 Clock Sense / Generated Clocks 章节：
[手册镜像](https://studylib.net/doc/27622832/synopsys%C2%AE-timing-constraints-and-optimization-user-guide)。

没有给无 reset 的 SRAM 增加初始化或清零。已经被适配层上升沿接受的写事务，
即使打包层在随后的半拍内复位，也仍在下降沿完成；未被接受的 pending 更新
仍遵从打包层的复位行为。

## 本地验证与服务器入口

本地 XSIM 使用明确标注的替身 `tb/models/kwt_ramtp_contract.v`：它只检查
逻辑行为及活动端口边沿至少相隔 3 ns，不包含工艺库插值或真实 row 映射。
三个深度的独立读写、跨 bank、局部写、同址连续更新、复位及新增半拍测试
已通过。故意恢复同沿时钟及故意直接传递写输入的两个对照均被测试拒绝。
这不是服务器真实宏验证结果。

当前包 `kwt_sram_phase_20261030_v8b.tar.gz` 不包含任何工艺模型或旧综合结果。
v8 首轮在服务器 Bash 4.2 的 `set -u` 下因展开空 `timing_options` 数组退出，
尚未启动 VCS 编译。v8b 改为构造始终非空的完整编译参数数组；RTL、时序检查
开关及综合预算不变。编译命令记录和实际执行共用同一个参数数组。
先运行开启 specify 检查的 150 MHz 短测试及两个存储回归：

```bash
mkdir -p ~/soc/kwt_sram_phase_20261030_v8b
tar -xzf ~/Desktop/kwt_sram_phase_20261030_v8b.tar.gz -C ~/soc/kwt_sram_phase_20261030_v8b
bash ~/soc/kwt_sram_phase_20261030_v8b/tools/run_kwt_sram_binding.sh --suite unit
```

短测试未通过时先看第一条诊断，不启动综合。短测试通过后，再运行：

```bash
bash ~/soc/kwt_sram_phase_20261030_v8b/tools/run_kwt_sram_binding.sh --synth
```

完整运行在新目录重跑全部四组仿真，再进行真实库综合；不复用旧 RTL 的
PASS、检查点或 hold pilot。本轮已确认 6336 个逐位匹配输出、3232909 拍和
40 个物理 RAMTP1024X16（80 KiB）。

`tb_kwt_sram_phase` 使用周期 6.667 ns，在时钟边沿之外驱动 A 输入，开启
真实宏 specify 检查，保留默认碰撞窗口，发现时序/碰撞诊断则报 FAIL。
其他三组是无 SDF 的理想 RTL 功能仿真，使用 `+notimingcheck`，其 PASS
不能替代物理 pin hold、宏时钟间隔或最终 STA。

综合继续读取独立的 `syn/kwt_encoder_12.sdc`，保留原 setup=1 ns、hold=1 ns
工程预算，避免同时改变 RTL 和裕量。该裕量不是赛题官方规定，最终依据仍需
明确。不会启动全局 hold 修复；DC 本次上限 30 分钟，超时保留日志并报失败。
普通寄存器 hold 可能仍为负，不因为宏时钟间隔改善而宣布全局闭合。

需要查看的报告：`timing_phase_clock_max/min.rpt`、
`timing_phase_write_max/min.rpt`、`timing_max/min.rpt`、`violators.rpt`、
`check_timing.rpt`。前两组要确认真实半拍边沿和锁存后写路径被分析。
面积、setup、hold 状态分别报告；工具执行完成不等于时序通过。
