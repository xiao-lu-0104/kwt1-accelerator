# 2026-11-05 当前共享 SRAM 加速器综合与报告恢复

用户执行已上传 `tpusoc_shared_asic_20261105_v2.sh` 并回传失败截图。
运行目录：`~/soc/tpusoc_shared_asic_20261105_gGGyZb`。

## 截图能确认的结果

- 源码关联检查通过，对应 shared_v1 的十七项成功功能回归及相同 NICE/TPU/ICB 模块。
- 厂商 Verilog、TT Liberty 校验通过，TT 私有 DB 转换已执行，DC 已读取标准单元及宏 DB。
- 综合映射及一次 hold 增量修复均已执行，`baseline` 和 `candidate` 的 DDC/Verilog/SDC 已保存。
- 随后在 `AssertSameReferences` 触发 `Outside-SRAM leaf count changed`，脚本非零退出。
- 因最终报告阶段尚未执行，当前 setup/hold、最终叶面积及候选接受状态均不能标记为通过。

这里是 SMIC40 TT、1.1 V、25°C、150 MHz 的布局前综合与时序检查。
TT 是工艺角条件；本次没有布局规划、布局、CTS、布线或带寄生的多角物理签核。
CPU 与平台共享 ITCM/DTCM 不在此次加速器面积/时序边界之内。

截图中的 `PWR-428` 是默认活动率传播时的未标注黑盒输出警告，
综合优化表内的 leakage 数值不是完整任务活动标注后的功耗结果。
`TIM-134` 的高扇出时钟提示保留为物理实现待处理事项，不能据此宣称已完成时钟树。

## 恢复方案

新增 `Server/SharedAsic/RecoverReport.py`、`Snapshot.tcl`、`RunReport.sh`、`MakeReport.py`。
生成自包含 `tpusoc_shared_report_20261105_v1.sh`，自动寻找与原 v2 工具清单及失败类型
匹配的运行目录，重新核对十七项功能证据、原源码、原库哈希，捕获已保存 checkpoint 哈希。
原目录、网表、DDC、约束及库保持只读，报告写入新的独立目录。

分别读取 baseline/candidate DDC，输出 setup/hold、SRAM 输入 hold、全部映射叶面积、
宏面积、设计/时序检查和逐单元变化表；额外保存层级外新增或替换单元的引脚/网连接。
报告完成后再判别时序与修复范围，不放宽层级外变化保护，不自动宣称等价性。
此脚本不重新 analyze/compile，不修改网表或约束，也不重新转换库。

七项恢复报告测试在 Windows、Linux 均通过；Tcl 语法与原 IO/时钟预算检查通过，
生成脚本通过 Bash 语法检查。本地测试是 mock/数据校验，不是 DC 执行。

已上传恢复脚本，FTP 226、curl exit 0。大小 24526 字节，SHA256：
`e5bdf6ba0872f8ec0526d9e32adeace53313b824c7bba863c8b54cb638ba8fd7`。

```bash
bash ~/Desktop/tpusoc_shared_report_20261105_v1.sh
```

## 恢复执行回传：布局前 TT 时序达标

用户随后回传 `RESULT: SHARED_SAVED_REPORTS_COMPLETE`，目录为
`~/soc/tpusoc_shared_report_20261105_J0U0qM`（大小写以服务器原路径为准；后续脚本自动查找）。
恢复程序重新核对输入源码、库和 checkpoint 哈希，确认未改动。

| 项目 | 原始映射 | hold 候选 |
|---|---:|---:|
| 全局 setup WNS / ns | 0.424492 | 0.424492 |
| 全局 hold WNS / ns | -0.120269 | 0.00112969 |
| SRAM 输入 hold WNS / ns | -0.120269 | 0.00112969 |
| 全部映射叶库面积 | 701526.678384 | 703272.383184 |
| 私有 SRAM 库面积 | 512317.367184 | 512317.367184 |

时序要求未变；恢复程序给出 `TIMING_STATUS: PASS_TT_PRELAYOUT`。
hold 余量约 1.13 ps，此结论限于既定 TT 和布局前工程预算。
原始面积保留库单位，尚不把该值当作 mm²；CPU/平台存储仍在边界之外。

完整差异统计：SRAM 范围内 296 项，范围外真实单元 37 项、伪常量 0 项。
截图显示的前 24 项均为 `Tpu/Core/U753...` 等新增 BUF 系列单元；
总计 37 项尚须程序完整核对，不能由截断的前 24 项外推全部性质。
当前保持 `SCOPE_REVIEW: REQUIRED`，没有声明网表等价或最终候选已接受。

`check_design` 截图末尾的 LINT-52 常量输出可由源码解释：
`TpuNice` 的 Status 高 26 位为零，响应数据为该 Status 或零；
`TpuIcb` 始终发 32 位访问，ICB size 固定为 2'b10。
这些不是仅因告警而需要改变的功能。截图末尾没有展示完整检查报告全部内容。

## 下一步：实际模型门级功能复验

新增 `PrepareGate.py`、`AuditCells.tcl`、`RunGate.sh`、`MakeGate.py`。
核对已完成报告的固定工具清单、原始输入及功能关联后：

- 检查所有层级外变化是否均为新增单元，原单元引用有无删除或替换。
- 从原 Liberty DB 读取每种新增单元的输入/输出及 Boolean function，验证是否非反相 buffer。
- 在原标准单元 DB 的同版库目录寻找实际 Verilog/压缩 Verilog 模型，记录覆盖和哈希。
  缺少模型时明确报告 `MODEL_INPUT_REQUIRED`，不自行编造标准单元模型。
- 有模型时，将原功能编译列表中的整个 NICE/TPU/ICB RTL 替换为保存的候选网表，
  保留真实 CPU/TCM 和 SRAM 厂商功能模型，运行独立 FF1 与单层编码器完整数值/流量检查。
- 保存模型和候选指纹；前后核对，原目录保持只读。

此步骤不跑新综合、不修改网表/约束；门级仿真关闭 timing checks，无 SDF，
不能代替形式等价、回标时序或功耗活动标注。本阶段未采集功耗活动。
五项模型选择/缺失处理/候选改动拒绝测试在 Windows 和 Linux 均通过，
新增 Tcl 完整性和 Bash 语法检查通过；这些不是服务器 VCS 已运行的证据。

脚本已上传，FTP 226、curl exit 0。大小 28210 字节，SHA256：
`c556cb1188f1579c4d6991155450a7aead0a03d52fadc7eb68b587e1d4bf2c51`。

```bash
bash ~/Desktop/tpusoc_shared_gate_20261105_v1.sh
```

## 门级执行回传：buffer 审核通过，FF1 功能失败

用户回传 `~/soc/tpusoc_shared_gate_20261105_rsVcYu` 的完整末尾。
原始输入、候选和报告关联校验通过，125 种标准单元引用在同版库中找到模型，
扫描 4 个 Verilog 文件，VCS 门级编译完成。

37 项层级外变化全部为新增，没有原有层级外引用删除或替换：

| 单元引用 | 新增数 | Liberty 输出函数 |
|---|---:|---|
| BUFV24RO_12TR40 | 2 | I |
| BUFV24RQ_12TR40 | 4 | I |
| BUFV32RQ_12TR40 | 23 | I |
| BUFV32_12TR40 | 8 | I |

脚本确认四种引用均为单输入、单输出、非反相 buffer。
这解释了原层级外数量保护为什么触发，但不代替完整网表功能或形式等价。

FF1 随后失败，尚未执行 encoder：
`CPU failed/trapped: done=4205843331 PC=80000500 error=00000000 cause=00000000 mepc=00000000`。
失败信息中的 done 并非固件约定的 0/1/2/3；`4205843331 = 0xFAB01383`，
与本地同包 `Ff1_normal/Input.hex` 第 2 行完全一致。
该匹配提示优先诊断读响应数据与总线时序，但目前不足以证明根因；
不将日志中的 failed/trapped 字样直接解释为 CPU 真实异常。
候选门级功能状态保持 FAIL，原 TT 静态时序结果不因此改写。

新增诊断 `PrepareGateDiag.py`、`GateWatch.sv`、`RunGateDiag.sh`、`MakeGateDiag.py`：
固定失败包工具清单和候选/库哈希，在新目录增加被动观察器，记录最后 24 个
外部装载器/NICE 访存与响应事件、真实 mailbox 内容、加载计数和 cycle。
先复现模型默认延迟，再用 VCS `+delay_mode_zero` 做零延迟功能对照；
若仍失败，自动运行相同库环境下的原 RTL 对照。
不驱动或 force DUT、不改候选/固件/CPU/原 SharedTest，也不放宽结果比较。
零延迟结果仅能说明功能，不作为 SRAM 延迟、计时、SDF 或功耗证据。

当前功耗、完整外设 SoC 与多角物理后端仍未完成。

诊断工具的五项指纹/失败类型/改动拒绝测试在 Windows 和 Linux 通过，
生成脚本通过 Bash 语法检查。观察器加入真实 CPU/TCM 的本地 RTL 后，
FF1 25344 个输出及所有计数匹配，332276 周期与此前本地结果一致。
该检查只验证新增观察器在本地控制环境未改变结果，不能替代服务器门级复验。
本地证据：`workspace/Checks/GateWatch/ff1.log`。

诊断脚本已上传：`tpusoc_gate_diag_20261105_v1.sh`，33698 字节，
SHA256 `abe150fa9ef84d7b86393561a9237b573f2d53fb827cca581c450de9e0b147fb`，
FTP 226、curl exit 0；服务器执行待回传。

```bash
bash ~/Desktop/tpusoc_gate_diag_20261105_v1.sh
```

## 延迟/RTL 对照回传：失败并非仅由默认模型延迟解释

用户回传诊断目录 `~/soc/tpusoc_gate_diag_20261105_FJhD1y`。
默认门级及 `+delay_mode_zero` 门级在同一 cycle 96753 失败；
原 RTL 在相同标准单元库环境中通过，完整 FF1 为 332348 周期。
这不是零延迟门级通过记录，候选网表功能继续保持 FAIL。

被动观察器显示：任务输入/参数装载已完成，LoadedWords=11490、DMA 只读了 2 字，
尚无输出写回；mailbox done 实值为 0，cause/mepc 也为 0。
外部读响应却出现 `FAB01383`，ready/valid 握手中出现 X。
因此仅凭旧 fatal 的 failed/trapped 文本不能判定 CPU 真实异常。
标准单元片段使用 10 ps 时间单位、1.0 的占位路径延迟；默认与零延迟对照相同，
不能把问题归结为这些默认延迟。

原 SharedTest 的 `do ... while (!CommandReady/ResponseValid)` 在四态仿真中
遇到 X 会退出等待，缺少未知值保护。新 probe 在隔离 testbench 副本中增加
unknown ready/valid/read-data 拒绝；原结果比较、总线传输和原平台不变。
这能更早指出未知握手，但本身不是对引起 X 的硬件/模型根因的修复。

新增 `PrepareProbe.py`、`IcbMirror.sv`、`RunProbe.sh`、`MakeProbe.py`：
分别测试原映射 baseline、hold candidate，以及仅将候选 ICB 模块换回原 RTL 的诊断对照。
前两份网表保持原字节；第三份明确标为定位用，不作为交付配置或等价证明。
被动 ICB RTL 镜像使用与被测 ICB 完全相同的输入，在稳定半拍比较有效控制/数据；
只在有效写事务比较 wdata，不将读事务中无意义的 wdata 未知值判为错误。
额外保存 ICB 映射模块、所用顺序单元模型头部及 VCS 编译警告供继续定位。

本地真实 CPU/TCM RTL 加入 strict 副本和镜像后，完整 FF1 通过：25344 值、
332276 周期、镜像 divergence_observed=0，与原本地结果一致。
证据：`workspace/Checks/GateProbe/ff1.log`。Python 编译与 Bash 语法检查通过。
这只验证诊断工具及本地控制环境，不证明服务器门级已恢复。

新脚本已上传 `tpusoc_gate_probe_20261105_v1.sh`，39539 字节，
SHA256 `812c5f2754d119b3b74d33d60ce28e82485d6576abcdb21c7b36fed21c6b2d22`，
FTP 226、curl exit 0。服务器执行待回传：

```bash
bash ~/Desktop/tpusoc_gate_probe_20261105_v1.sh
```

## Probe 回传：baseline/candidate 均失败，镜像输出信息不完整

用户回传目录 `~/soc/tpusoc_gate_probe_20261105_UvKBQ4`。
baseline 与 candidate 都在 cycle 96746 被新增严格检查以
`UNKNOWN_LOADER_COMMAND_READY` 终止，比旧完成码错误更早。
所以功能失败在 hold 修复之前已存在，不能归因于新增 37 个 buffer。

两者的 ICB 镜像在 cycle 96741 报首处分歧，但打印出的 actual/expected
control 都是 000010，地址/读方向及无效 read-data 也相同。
原比较还包含未打印的 `IcbCommandSize` 两位，因而这条日志尚不足以定位真实分歧；
综合内部未使用端口也可能与顶层实际连接不同，须结合网表核对。
不据此断言 ICB 状态机已发现错误。

bus_rtl_control 的日志只出现 DIAG_START，无 PASS、fatal 或 final 记录；
原运行器将异常退出、超时和数值失败都汇总为 FAIL，未保存单独退出码。
因此该项状态应记为“未完成/疑似超时，需检查”，不能当作与另外两项相同的失败。

为了避免继续运行信息不完整的长对照，新增只读 `ReadProbe.py` 和独立上传脚本。
读取并核对既有 probe 指纹后，打印实际 Bus 连接、模块声明、size 相关连接、
状态/word/direction 等控制触发器实例及厂商顺序模型功能部分、编译告警和日志结束标志。
不启动 VCS/DC，不修改原目录或模型。原始模型中未绑定输入只作为原始声明提示，
明确需要结合条件编译判断，不直接宣称缺少物理电源连接。

三项网表/嵌套连接/输入声明解析测试在 Windows 和 Linux 通过，
脚本通过 Python/Bash 语法检查。读取入口已上传，FTP 226、curl exit 0：
`tpusoc_read_probe_20261105_v1.sh`，6603 字节，
SHA256 `81c3cf1ae4f5da7ec7af3ae3b214c5eca6813c26571d21c2894e81fb99eac32c`。

```bash
bash ~/Desktop/tpusoc_read_probe_20261105_v1.sh
```

等待现有网表/模型片段回传；候选门级功能仍未通过，不改变原 TT 时序记录。

## 只读片段回传：确认镜像对子模块 size 的误报

用户回传实际 `TpuIcb Bus` 连接与定义。综合顶层直接将
`nice_icb_cmd_size[1:0]` 赋为 2'b10，Bus 的 `IcbCommandSize` 没有连接，
子模块保留该输出声明但没有驱动。原镜像把这个未使用子端口与 RTL 的 2'b10 比较，
因此 cycle 96741 的首个 mismatch 不能作为功能故障起点。这是诊断器错误，已修正。
镜像改为比较顶层真正送到 CPU 的 size，并同时打印 top/child/reference 值。
实际 strict ready-X 失败仍然存在，没有因修正镜像而被豁免。

控制寄存器使用 DQV0_12TR40，映射连接 CK/D/Q 与原厂模块端口相符；
厂商模型内 xSN/xRN 为 supply1，没有依据要求用户补这类物理电源输入。
原始 TFIPC 片段包含被优化未连接的模块/单元输出，不能将所有 TFIPC 当作缺输入；
仍需结合实际端口逐项区分。
混合对照文件仅有 341 字节，无 PASS/fatal/final，确认没有正常完成记录，
但旧脚本未记录退出码，仍不凭该片段断言具体超时原因。

新增小测试与修正镜像入口：`PrepareSmall.py`、`GateCellSmoke.sv`、
`GateIcbSmoke.sv`、`RunSmall.sh`、`MakeSmall.py`。
连续检查实际 DQV0 模型在不加载/加载 SRAM 模型两种编译环境下的时钟采样与保持，
隔离的真实映射 ICB 首 8 字/2 beat，以及带修正镜像的原候选整机。
隔离 ICB 保留整个候选文件的算术辅助模块定义，只 elaborates 测试所需的 ICB。
新增保存关键控制 D 输入的组合锥，区分 PASS/FAIL/TIMEOUT 并记录退出码。
小测试 20 秒限时；整机定位限时 180 秒，不再次等待 15 分钟混合测试。

本地原 RTL 的 ICB 小测试 20 周期、8 字/2 beat 通过；修正镜像加入真实 CPU/TCM
完整 FF1 后仍为 25344 值、332276 周期、divergence_observed=0。
本地证据为 `workspace/Checks/GateSmall/local.log` 及 `workspace/Checks/GateProbe/local_v2.log`。
Python/Bash 语法和 diff 检查通过，本地没有厂商标准单元功能验证能力。

已上传 `tpusoc_gate_small_20261105_v2.sh`，28016 字节，
SHA256 `93390d762c6690b903085946c4f5e92c799b51576205190b80702409988a9bd4`，
FTP 226、curl exit 0。等待实际小测试回传：

```bash
bash ~/Desktop/tpusoc_gate_small_20261105_v2.sh
```

v2 在终端摘要中明确打印全部 ICB_FINAL_* 状态，避免被后续 ring trace 挤出。
此前 v1 仅上传，未交付执行命令，保留作版本记录。

## Small v2 回传：真实失败已隔离到映射 ICB

用户回传 `~/soc/tpusoc_gate_small_20261105_kN6Imv` 的结果与两个 run.log 尾部：

- cell_std / cell_sram 均 PASS：普通 DQV0 时钟采样、低电平期间数据变化保持正常。
- icb FAIL：第 7 个非复位周期、已接收 2 字/0 beat，
  `ICB_UNIT_UNKNOWN_CONTROL req=x read=x cmd=x rsp=0`，时间 145000 ps。
- full FAIL：cycle 96746，预期 State=010、Word=10，实际 State=xx0、Word=xx。
  实际总线地址仍为 90001008、读方向为 1，控制含 X；真实 DTCM done 仍为 0。
  顶层 size=10 与参考一致，子模块未使用 size=zz；此前 size 检查器误报已消除。

隔离测试没有 CPU、共享 TCM 或仲裁器，因此本次可确认映射 ICB 自身/其模型编译环境
已经能够复现故障。baseline/candidate 的既有对照也说明失败先于 hold 修复。
现有证据尚不能区分组合逻辑/端口驱动问题与带反馈的顺序模型行为，不能宣称已经找到根因。

新增 `PrepareCone.py`、`GateFeedbackSmoke.sv`、`RunCone.sh`、`MakeCone.py`：

1. 打印实际库中 `udp_dff` primitive 表，测试真实 DQV0 的计数反馈及 CK 高期间 D 改变后的保持。
2. 只对隔离映射 ICB 每拍记录 State/Word/控制寄存器的时钟前 D/Q 与时钟后状态。
3. 在时钟边沿后及稳定半拍扫描组合单元，记录已连接输入都已知、输出却 X 的单元，
   同时列出原始未连接输入（仍需结合条件编译审核），并打印对应真实模型功能段。
4. 对照真实模型的 `functional` 编译分支；另在明确标注的副本中仅把 ICB 内 DQV0
   替换为正边沿 NBA 参考触发器，以隔离顺序模型语义。这个副本只作诊断，绝不作为交付网表。

原候选、源码和厂商模型均保持原字节，运行前后核验指纹；不运行综合或整机。
四项小测试编译各 5 分钟限时、仿真各 20 秒限时。
新增 Python 观察器测试 2 项及原解析测试 3 项通过；实际生成的观察器（含 DC 转义实例名）
和反馈测试在明确标记的本地合成单元 fixture 下编译/运行通过。
本地仅验证诊断程序，不验证厂商模型；检查目录为 `workspace/Checks/GateCone`，
本次 native 构建目录 `/tmp/tpusoc_cone_check_ph13vE`。
生成脚本 Bash 语法、Python 编译及 git diff 检查通过。

已上传 `tpusoc_gate_cone_20261105_v1.sh`，22490 字节，
SHA256 `e28741c96ce2d643dcc8616ce9cd0d3dabdb56675946c57113a4b7d1dcd7b05a`，
FTP 226、curl exit 0。服务器执行待回传：

```bash
bash ~/Desktop/tpusoc_gate_cone_20261105_v1.sh
```

## Cone v1 回传：Word 先出现 X，NBA 触发器对照同样失败

用户回传目录 `~/soc/tpusoc_gate_cone_20261105_QRQvHS`：

- feedback PASS：实际 DQV0 的 20 次计数反馈与 CK 高期间数据改变保持测试通过。
- real / functional / nba_diagnostic 均 FAIL，仍为 2 字/0 beat、非复位 cycle 7。
- 日志尾部显示 edge 10 后 State=010、Word=0x，随后 Word=xx，edge 14 后 State=xx0。
  因此前面的 ready-X 是传播结果，不能作为最早根因；需要读取完整日志中的第一次 X。
- 全部 ICB DQV0 替换为独立 NBA 参考触发器后故障位置仍相同，
  现有对照不支持把问题归因于 DQV0 的反馈行为；重点转向 Word D 输入的组合逻辑及连接。
- UDP 表已回传，包含输入改变时保持、下降沿保持、上升沿采样等条目；
  未修改厂商 UDP 或正式网表，不把诊断副本当作修复。

原运行器仅显示末 45 行，最早 Word-X 前的 D 输入上下文不在当前截图中。
终端未见 CELL_XSOURCE 模型摘要，不能因此宣称所有组合逻辑均正确。
为避免重复编译，新增只读 `ReadCone.py` / `MakeReadCone.py`：
核验已完成 cone 输入和内嵌工具指纹，提取每种模式第一次状态/Word-X 的前后上下文；
从 Word 两位 D 输入出发，遍历实际映射网表至触发器或外部输入边界，
打印常量、未解析表达式、多驱动/组合环提示及所有相关真实单元模型功能段。
读取范围不包含时序弧，不调用 EDA 工具；所有原网表、模型和日志保持原字节。

新增两项测试覆盖第一次 X 提取及含转义 FF 名的完整已保存输入/模型读取流程，均通过。
Python 编译、生成脚本 Bash 语法与 diff 检查通过。
读取入口 `tpusoc_read_cone_20261105_v1.sh`，6690 字节，
SHA256 `1441f028de3ce962608c83b72790fb1aa5f13b88c8ab9465ef12b4c338abce66`。
已上传：第一次被动数据连接超时，第二次 FTP 226、curl exit 0。服务器读取待回传：

```bash
bash ~/Desktop/tpusoc_read_cone_20261105_v1.sh
```

## Read cone 回传：复位期间 Word[0] 的反相汇合造成 X 悲观传播

用户回传完整 Word D 输入组合锥、实际单元功能段及首次 X 上下文。
NBA 对照 edge 1 的复位前 Word[0].D=X，复位后 State=000、Word=0x。
这纠正此前故障起点的判断：两次读响应后的 ready-X 是可见失败位置，
Word[0] 未知值在复位期间就已经存在。

实际门函数及连接给出，ResetN=0 时：
n155=1、n174=0、n304=1、n303=0、n177=1、n623=1、n574=0。
n176=~Word[0]，n552=(n177 & n574 & n176) | (Word[0] & n176)，
因此实际 Word[0] D 输入为 `Word[0] & ~Word[0]`。
初始 0、1 的二态结果均为 0；初始 X 在普通四态门模型下仍为 X。
这是复位逻辑经过优化后反相信号重新汇合的 X 悲观传播，
并不是由触发器 UDP 反馈本身造成。完整推导见 `Doc/GateReset.md`。
这是一项有具体逻辑依据的原因定位；尚未证明它解释了后续全部任务失败。

新增有明确初始条件的 `PrepareBoot.py` / `RunBoot.sh` / `MakeBoot.py`：
运行前严格核对相关九个门和 Word[0] 触发器连接，只在一个复位时钟期间
给该触发器 Q 选择二态初值，随后永久释放。两种初值均需真实 D0=0、
释放后连续复位检查 Word=00/State=000，再完成 ICB 首 8 字/2 beat。
两项通过后，复用原完整网表编译，跑 FF1 两种初值和单层编码器初值 0。
保持 strict 握手、完整黄金结果、输出越界、DMA 计数及无分歧 RTL 镜像检查。
不改任何 RTL/候选/厂商模型，不重跑综合，不在任务期间持续 force，
不将有初始条件的结果标为全 X 初始状态自然复位通过。

生成的 reset-only force/release 流程在本地明确标注的合成单元 fixture 下，
初值 0/1 均编译运行通过，目录 `workspace/Checks/GateBoot`，
本次 native 构建 `/tmp/tpusoc_boot_check_D0U55M`。
本地不提供实际四态厂商模型结论。Python 编译、Bash 语法及 diff 检查通过。
上传入口 `tpusoc_gate_boot_20261105_v1.sh`，35589 字节，
SHA256 `37495e4671be7be36f9de835cda72dea61b7301dbd011431feb369e8453140bd`。
已上传：首次被动数据连接超时，第二次 FTP 226、curl exit 0。
实际服务器复位与完整功能结果待回传：

```bash
bash ~/Desktop/tpusoc_gate_boot_20261105_v1.sh
```

## Boot v1 回传：第一处 X 已解除，整机仍有后续未知值

用户回传 `~/soc/tpusoc_gate_boot_20261105_NXiRq3`：
九门组合锥与真实 Word[0] FF 连接检查通过；初值 0/1 两项隔离 ICB 都完成首 8 字/2 beat，
释放 Q force 后 Word=00、State=000，支持已定位的 Word[0] 复位 X 问题确实存在。

整机 ff1_seed0 已验证该位复位清零，但在 cycle 96833 再次因严格 ready-X 检查终止。
DMA_read 已从此前的 2 提升到 36，DMA_write 仍为 0；
cycle 96831 的镜像首处分歧中 actual/expected control 均为 010000，
所以不能据此直接推断是状态控制首先错误，还需检查有效 read-data/last/error。
最终实际 State=0xx、Word=xx，参考 State=011、Word=00，ReadReady 也为 X。
剩余结果未运行：ff1_seed1 与单层编码器被运行器的失败即停策略跳过。
本次明确表明 Word[0] 不是完整的单一根因，不宣称整机功能已恢复。

新增 `PrepareInventory.py` / `RunInventory.sh` / `MakeInventory.py`：
对原加速器映射层级遍历实际厂商 DFF 模型，枚举 Q/D/时钟连接，排除 CPU 和 SRAM 数组。
未覆盖的时序端口、非 SRAM 不透明叶模块或过程描述的候选模块会直接停止，
不在覆盖不完整时宣称已初始化全部映射触发器。
新观察器一次性记录复位期间残留 X 的全部 FF 至文件，终端优先显示 ICB/DMA 控制寄存器；
任务中在稳定半拍记录控制 Q 首次从已知值变成 X 时的先前/当前 D 与所在路径。
每次失去已知值只报一次，最多 24 条，保留原最终失败与黄金结果检查。

同一编译依次运行原 Word[0] 单位初始化的失败参照，以及全部映射 FF 的全 0、全 1、
按层级名 SHA256 固定生成的随机图样。所有初值只通过一个复位时钟的 Q force 施加，
随后永久释放；CPU 和 SRAM 数组不直接初始化，不替换候选或厂商模型。
完整 FF1 三种图样全部通过且 ICB 镜像无分歧后，才运行固定随机图样的单层编码器。
这些结果只描述指定初值下的功能，不能替代无初始化、形式等价或 SDF/物理时序验收。

本地三项测试覆盖层级和转义实例、未映射过程模块拒绝、未支持时序端口拒绝，全部通过。
生成的全部模式（Word-only、全 0、全 1、固定随机图样）在明确标注的本地合成单元 fixture 下，
完成编译、一个复位时钟的初始化/释放及观察器检查；这不验证实际四态厂商行为。
目录 `workspace/Checks/GateInventory`，native 构建 `/tmp/tpusoc_inventory_check_AoVeKt`。
另对错误信息优先级作了调整，使未覆盖时序模型的报错优先于“未找到 FF”。
Python 编译、Bash 语法和 diff 检查通过。
入口 `tpusoc_gate_inventory_20261105_v1.sh`，30130 字节，
SHA256 `54c5fa5d782294966baf5df5af3af6f419da07e12aac1d4a71b24230f0033811`。
初次上传八次连接均提前超时；禁用 curl 默认配置的诊断重试显示 FTP 421，尚未上传成功。
随后通过未登录的控制连接读取到服务端横幅：
`421 There are too many connected users, please try later.`，
等待并重试仍为 421。这是服务端连接人数上限，不是脚本或认证通过的证据。
因此本入口不能标为已上传。

已生成不依赖 FTP 的备用 `workspace/Server/tpusoc_gate_inventory_20261105_v1.paste.txt`，
13264 字符单行命令，使用 gzip/base64 传递脚本正文。
服务器端只用已有 Python 3 标准库还原，并核对完整 SHA256；
若同名文件已经存在但内容不同就停止，避免覆盖其他版本。
校验和写入成功后，通过 `os.execvp` 执行这个完全相同的脚本。
本地已验证解压字节与原入口完全一致，生成粘贴命令的 Bash 语法检查通过。
服务器执行仍待用户粘贴后的日志，不将本地生成命令当作远程运行。

本机 Windows PowerShell：

```powershell
Get-Content 'E:\chipdesign\2026TpuSoc\workspace\Server\tpusoc_gate_inventory_20261105_v1.paste.txt' -Raw | Set-Clipboard
```

随后在服务器 VNC 终端粘贴并执行；日志先打印 LOCAL_TRANSFER_OK 和 SHA256，
再运行原 inventory 入口。输出目录仍为 `~/soc/tpusoc_gate_inventory_20261105_*`。

## Inventory 回传：三种初态 FF1 与单层编码器门级功能通过

用户通过 VNC 粘贴备用命令完成执行，回传完整终端摘要。
目录：`~/soc/tpusoc_gate_inventory_20261105_fA7tXq`。
本条是实际服务器结果，覆盖此前“备用命令已生成但未执行”的状态；
不将 FTP 失败的传输记录改写为 FTP 上传成功。

| 任务 | 初始条件 | 结果值数 | 完整任务周期 | DMA 读字节 | DMA 写字节 | 装载字节 | 结果 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| FF1 | 全部映射 FF 全 0 | 25344 | 332348 | 45952 | 50688 | 45960 | PASS |
| FF1 | 全部映射 FF 全 1 | 25344 | 332348 | 45952 | 50688 | 45960 | PASS |
| FF1 | 按层级名固定随机图样 | 25344 | 332348 | 45952 | 50688 | 45960 | PASS |
| 单层编码器 | 按层级名固定随机图样 | 6336 | 1485712 | 112256 | 12672 | 112264 | PASS |

四项通过任务均为原映射候选、实际标准单元模型、厂商私有 SRAM 模型及原 E203 CPU/LSU/TCM。
枚举 FF=19695，其中被动观察的控制 FF=274。
每次初始化只持续一个复位时钟，7000 ps 时永久释放，之后无 DUT 强制驱动；
完整数值、边界、DMA/命令计数和严格未知握手检查保留。
所有通过项均 `released=1 checked=1`、`new_control_QX=0`、
`ICB_MIRROR_FINAL divergence_observed=0`。
最终 ICB State=000、Word=11 与参考一致；子模块未使用的 size=zz 保持不作为错误，顶层实际 size=10。
周期和流量与此前真实平台 RTL 功能结果相同，没有用强制信号跳过装载或计算。

复位快照仍有 256 个非控制 FF 的 Q 为 X，控制 Q 未知数为 0。
截图尚不足以认定这 256 位的具体用途；本次通过任务未出现数值或协议可见错误，
不能将此外推为所有任务/状态下均无影响。

`word0_reference FAIL exit=0` 保留为参照：只初始化 Word[0] 仍失败；
运行器通过 fatal/结果标志判断失败，不将 VCS 退出 0 当作功能通过。
因此这次取得的是“在指定二态初始条件下的门级功能通过”，
不能写成“全 X 初始状态可以自然复位通过”。
未提供形式等价、SDF 回标、布局布线或多角签核结论；十二层编码器尚无本轮门级通过证据。

本轮截图已足够核对三种 FF1、单层编码器、无分歧镜像、任务周期及初始化释放条件，
无需再索取相同结果截图或重跑本轮功能。
后续主项转为同一候选配置的任务活动采集、活动覆盖/SRAM 模型核对、功耗估算和交付材料。
功耗报告尚缺，不能用此前 DC 优化表 leakage 或默认活动率替代。
