# SMIC40 TT 综合与时序，ASIC v3

上游固定 `a1d0c9aa5f6f549b2f637f96be6a6e5ed305ce00`，无跟踪的 RTL 修改。
CPU 子模块固定 `9f3e34f337f5d0a1236a285871ffa2032491617a`。
本轮是 DC 逻辑综合与真实库 STA，不含布局布线、CTS、寄生提取和多角签核。

## 宏绑定依据

用户回传 `tpusoc_sp_audit_LkxaaS` 的端口及手册片段。
`RAMSP1024X16` 为单时钟上升沿访问；CEN、GWEN、WEN 低有效；
GWEN=1 时读，GWEN=0 且 CEN=0 时写；写透关闭时写操作保持 Q。
RET1N=1 正常访问。TT 手册默认 EMA=2、EMAW=0。

候选适配层 `SpFoundry.sv` 使用原 bank 的 `en/write/addr/wdata/rdata` 接口：

| 宏端口 | 连接 |
|---|---|
| CLK | 原 Clock，上升沿 |
| CEN | ~en |
| GWEN | ~write |
| WEN[15:0] | 16'h0000，整片 16 位写；外层 bank 使能负责写掩码 |
| A / D / Q | addr / wdata / rdata |
| EMA / EMAW / RET1N | 2 / 0 / 1 |

沿用 `TPU_SRAM_MODEL` 选择原显式 bank 分支，但源码列表以 `SpFoundry.sv` **替换**通用行为模型。
综合不读厂商行为模型，不读通用数组实现，直接把 `RAMSP1024X16` 引用链接到真实 DB。
默认采用厂商逻辑端口模式，不定义 POWER_PINS，不显式连接电源口。
保留原请求流水、输出寄存器与完整周期时钟，没有新增半拍时钟。

必须得到 7×8=56 个宏，112 KiB。审计 TT Liberty 单宏 area=9148.524700，
宏面积合计 512317.3832 **Liberty area 单位**；总面积以 DC 报告为准，不先宣称芯片面积达标。
`VerifyMacro.py` 核对用户已回传的 Verilog 和 TT Liberty SHA256，防止同名文件漂移。
私有 DB 从该确切 Liberty 转换；不修改共享工艺库。

## 运行顺序与验收边界

```bash
bash Server/Backend/RunAsic.sh
```

默认先跑 TPU 150 MHz，再跑 CPU 150 MHz / TPU 150 MHz；集成版仍为两个独立时钟。
可显式运行其他 CPU 档作诊断，TPU 保持 150 MHz，例如：

```bash
bash Server/Backend/RunAsic.sh --top soc --cpu-mhz 50
```

1. 校验包内清单、厂商模型与 Liberty 哈希。
2. VCS 编译真实宏＋候选适配层＋原 TpuSram，验证 56 banks、首尾地址、双逻辑读口、
   全部 256 种 bank 写掩码、写后读、空闲不写与精确读流水，共 568 个读回值。
   此为 RTL 功能测试：使用 `+notimingcheck`，保留模型路径延迟，未用 `+nospecify`。
   零延迟 RTL 发射寄存器不能用于证明宏 hold；实际 setup/hold 由后面的真实库 STA 检查。
3. VCS 原生运行原 `CdcTest`，1024 个异步包、气泡、反压与复位。
4. Library Compiler 转换私有 TT DB；无独立 lc_shell 时以 dc_shell 尝试，仍需 LC 许可。
5. 分别运行两个顶层的 DC。验证真实宏计数及所有非恒值叶单元已映射到库，输出网表、
   SDC、DDC、面积、全局与各时钟域 setup/hold，以及 CDC 两方向数据包路径。

先保存 mapped DDC；报告出错时可据此恢复，避免重复综合。
`REPORTS_COMPLETE` 只表示工具执行完成；负 WNS 仍打印 FAIL。未启动全局 hold 修复循环。
VCS 编译每项限 5 分钟、Lib 转换限 10 分钟、DC 每个顶层限 30 分钟。

## 独立约束及 CDC

没有官方 SDC。当前是明示的初始工程预算，**不是比赛验收或时序签核依据**：

| 项目 | 当前值 |
|---|---|
| TPU 周期 | 6.666667 ns |
| CPU 周期 | 默认 6.666667 ns，可显式选 20 / 10 ns |
| setup / hold uncertainty | 0.2 / 0.1 ns |
| 输入 / 时钟 transition | 0.1 ns |
| IO max delay | 1 ns |
| 输入 min / 输出 min delay | +0.1 / -0.1 ns |
| 输出 load | 0.035，使用已载入标准单元库的电容单位；见 units.rpt |

CPU ICB/调试端口属于 CpuClock，AXI 属于 TpuClock，分别约束。
同时输出同域寄存器到寄存器的内部余量，避免把暂定 IO 预算与内部关键路径混在一起。
集成版外部 ResetN 按公共异步断言处理，两个域分别同步释放复位；
独立 TPU 顶层没有内置复位同步器，因此 ResetN 保留 max/min 输入预算，不设置 reset false path。

不设置全局 asynchronous clock group。DC 先做低努力映射以得到每一位的实际 D 引脚，
避免猜测未映射 GTECH 总线寄存器的引脚名；删除该阶段的临时跨域约束后，
仅切四个 toggle 同步器第一级 D，保护并核对八个同步器 FF。
两级内部路径仍保留同步时序检查。

请求／响应 payload 各设置接收域一个周期的 max-delay，使用 Synopsys
`-ignore_clock_latency`，以及 min-delay=0 来取代异步域之间没有物理意义的固定相位关系。
仅作用于两条握手 payload 通路。同步域 hold 不受该例外影响。
源数据直到 ACK 返回才允许覆盖；这一协议假设由原 RTL 和 CDC 功能测试覆盖。
方法参考 [Tenstorrent 的 DC CDC 约束说明](https://docs.tenstorrent.com/tt-oca-harness/ocah-integrator-guide/latest/cdc.html)。

DC 结果不写成 bus-skew 或亚稳态 MTBF 签核。真实布线后的偏斜、时钟树及 CDC 结构审查仍待物理流程。
E203Tpu 边界外的 TCM 控制器/存储、DDR 控制器/PHY 不在这次面积和时序范围内。

## 本地证据

`LocalBindingTest.sh` 用明确标注的 `LocalRamspFixture.sv` 替身检查适配层，568 个读回值通过。
服务器运行器从不编译该替身，只编译共享库中的确切厂商模型。
`TestConstraints.tcl` 用模拟 collection 测试 CPU/AXI 端口分域、四个第一级 D 例外和两个 payload 预算，
不是 DC 执行。Tcl 完整性、Bash 语法亦检查通过。
厂商功能及真实库 DC 结果必须等服务器本次日志，不能用本地替身结果代替。

## v3b 分析失败后的恢复

服务器已确认实际厂商宏 568 个读回值、原生 CDC 1024 包及 TT 库转换均通过。
DC 在 `SpFoundry.sv` 中未使用的 `parameter real TCO` 处报 VER-177。
修复仅删除该参数及前一行的逗号，原宏实例、连接和时序预算不变。

独立的 `tpusoc_asic_fix_20261102_v3c.sh` 可直接在服务器用 Bash 执行，传入原工作目录。
它核对 v3b 包清单、所有原项目源文件、通过记录与缓存库哈希，
复制至原工作目录下的新恢复目录，在副本中做精确两行替换，复用原 DB 只重跑 DC。
原运行目录的文件不覆盖。工作记录 `recovery.json` 保存修复前后哈希。
本地三项 fixture 测试覆盖精确修改/保留原文件、拒绝变化的 RTL、拒绝变化的缓存 DB；
修正后的适配层通过 Verilator lint，服务器 DC 实测仍待回传。
