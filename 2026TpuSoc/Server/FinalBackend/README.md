# 决赛形式验证与物理实现入口

最新服务器v5：`tpusoc_formal_accelerator_20261108_V4RHfb`，333秒收集完成，原生
GUIDANCE_READ_RETURN=1、MATCH_RETURN=1、VERIFY_RETURN=1；冻结输入未改。
结果TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING，加速器工具比较已通过；
数组147索引安全、比较/宏边界及指导constraints/environment仍待审，CPU/共享TCM未在本轮比较。
指导接受reg_merging13项、reg_constant164项；change_names拒绝2项，表内无unsupported/unprocessed。
PR v4已在mTq1LE实际完成两个NDM和ICC2导入/初始floorplan：71,809叶、unbound0、56宏，原输入未变。尚无放置/布线。旧候选包未纳入本轮新增FM归档。

## 下一阶段：初始粗放置

`MakePrCoarse.py`生成`tpusoc_icc2_coarse_20261108_v1.sh`，46,652B，SHA256
`d471c4183621005990bd0cd9933ed5551b1719acb55aea5d57d1923f1693127a`。
上传器`-Stage coarse`，服务器`bash ~/Desktop/tpusoc_icc2_coarse_20261108_v1.sh`。
固定验证mTq1LE成功阶段及输入/log/工作区证据，当前SHA快照并复制设计库和两个参考库；
打开副本/改参考到副本，执行最多4核的`create_placement -floorplan -effort low`，保留逻辑实例/引用，
独立核对56宏native bbox/DEF放置状态/矩形core边界/零重叠以及原库未变。
输出新设计副本、DEF、MacroGeometry、SRAM分布SVG与诊断归档；原FRAM-066及PG/RC/CTS/route审查保留。
Linux20项（6粗放置+14原PR）通过；Windows粗放置5项通过、Tcl外部解释器替身1项跳过（Linux已通过）。
载荷/源码SHA、隔离导入、Python3.6/Bash语法及上传器CheckOnly通过，实际服务器粗放置待回传。
详见[范围、检查和操作](../../Doc/ICC2初始粗放置_20261108.md)。

## 首次实际ICC2入口

`MakePrStart.py`生成`tpusoc_icc2_start_20261108_v4.sh`，49,933B，SHA256
`af4368f057f6c56a202b7448fecdeb867ae8d6c866f5507b4747e0954b23cf80`。
上传器`-Stage pr`发送此入口，服务器`bash ~/Desktop/tpusoc_icc2_start_20261108_v4.sh`。
从原生FM通过记录和现有物理清单核对输入，实际构建独立RVT/private NDM、ICC2链接冻结加速器，
核对0未解析/56宏，连接逻辑PG并初始化floorplan和DEF。RVT层栈试用PDK 8lm_1tm标识；
无厚度/层映射验证时不加载RC，不做宏放置/PG路由/CTS/信号布线/时序签核。
Windows/Linux各9项PR编排测试通过，与形式流程合并各21项通过；服务器实际结果尚待回传。
详见[阶段/操作/接受范围](../../Doc/ICC2首次导入_20261108.md)。

v2已实测6秒在普通/antenna几何LEF双候选处停止，尚未LM/ICC2导入。
v3对精确同目录普通/_ant配对做限时SHA和完整非天线token比较，通过才选_ant；
其他几何/引脚/PG/层等差异停止并保留上下文，源文件不改。新增LefVariants.py子进程。
v3服务器RRkBI5实际LEF对比通过，RVT检查创建1276 frames并明确succeeded、无design mismatches；
原生返回空值被旧Tcl/Python误判，未commit。v4改为原生成功+无不匹配+default策略多项核验，
空值仅凭上述证据接受，false/未知/无证据/错误仍拒绝，保存报告SHA及FRAM-066警告数量。
失败自动输出原生报告尾部。Windows/Linux各14项PR流程测试通过，v4服务器待执行；原FRAM-066路由可达性审查保留。

`MakePreflight.py`生成冻结候选包的只读检查入口，使用`SystemBackend/UploadInitialMaterials.ps1 -Stage backend`上传。
服务器运行`bash ~/Desktop/tpusoc_final_preflight_20261108_v4.sh`。

检查绑定成功候选包SHA、内部manifest、对应DDC/修正SDC/三种DB及网表，
收集FM/Innovus/ICC2/PT/DC的实际帮助和可用路径，按工具真实help支持的脚本标志尝试FM文档会话。
扫描限定的标准单元/SRAM目录，记录LEF、routing层、site、两个SRAM的PG引脚及技术/RC候选文件。
源码扫描统计的是结构引用名，不冒充展开后的物理实例数量；实际PR导入必须重新核验。
扫描截断与缺项明确记录，文件存在不意味着版本/工艺兼容或许可证可用。

没有综合、match/verify、布局、CTS、布线或物理签核。输入与旧包保持不变，日志落在新目录。
后续实际FM和PR脚本依赖本轮服务器真实工具语法及工艺资料，当前未宣称已完成。
完整计划见[决赛提交物推进](../../Doc/决赛提交物推进_20261108.md)。

当前v4恢复入口21,238B，SHA256 `96241d21ad3cf47c23495da6ea72f452bd3af1edb7f9569e4ed3585d7fa895d5`。
Windows10项通过、3项POSIX跳过；Linux13项通过，包括阻塞LEF读取、阻塞目录扫描与部分清单恢复。
v2在服务器目录`tpusoc_final_preflight_20261108_X38FWC`运行5秒失败：
Python3.6遍历`/eda/cadence/innovus`抛出PermissionError，未开始FM或PR。
v3记录权限错误并跳过该目录，不更改权限，不把无法检查误报成工具不存在；继续检查其他工具和可访问PDK。
v3在服务器`tpusoc_final_preflight_20261108_E4ELtX`执行600秒exit124，已跳过Innovus权限问题，
调用FM/ICC2/PT/DC帮助与FM文档探测后停在PDK阶段；尚未定位是哪个目录或LEF操作阻塞。

v4自动选择已保存FM文档日志的已知v3目录，校验旧Preflight.py的固定SHA及FrozenInputs与当前候选一致，
复用帮助/文档日志。旧运行的退出状态无法从裸日志恢复，明确记为`RECOVERED_LOG_EXIT_STATUS_UNKNOWN`，
文档会话标记也不代表等价验证通过。新结果立即保存`ToolsInventory.json`。
两个PDK根各用独立进程35秒上限扫描，目录间保存部分清单；每份LEF独立进程12秒上限，
LEF合计90秒；LEF解析改为逐行单遍。超时项/缺项保留为未知或截断，不使工具检查结果丢失，
也不把“收集完成”当成物理资料齐备。总上限5分钟，原成功材料包与旧日志不改。
新输出另含`PhysicalInventory.json`、各扫描/解析子进程日志及部分JSON。

11月8日v4服务器实测20秒exit0，目录`tpusoc_final_preflight_20261108_sCgoD1`（以原输出为准）。
冻结候选不变；FM文档会话标记True、ICC2可执行文件已找到，Innovus目录仍权限拒绝。
技术LEF候选27、两类SRAM各1、引用LEF缺项0、技术/RC候选795、SVF候选1；
扫描/解析均无错误、无截断。工具日志是恢复证据，其原退出状态未知；尚未运行等价验证或P&R。
接下来须查真实工具路径/手册、SVF匹配关系及兼容技术/RC配置，不能从27/795候选中随意取首项。

## 实际加速器FM入口

`MakeFormal.py`当前生成`tpusoc_formal_accelerator_20261108_v5.sh`，36,158B，SHA256
`f30a105a7ed32208759e6f86a25c6faae227851f72a129a9507077cd837b9c06`。
上传器增加`-Stage formal`，旧`backend`仍指v4预检查，`initial`/`replay`保持原入口。
自动读已完成预检查的真实工具路径与安装手册，不再要求手工抄写路径。
核对16个原综合源、冻结网表和技术库后执行真正match/verify，保留失败和超时诊断。
原生verify返回真后也只记录`TOOL_VERIFY_TRUE_REVIEW_PENDING`，待审查比较点与宏边界。
总25分钟/FM20分钟上限，顺带ICC2文档会话75秒；不执行P&R，不重新综合或仿真。
详见[加速器形式验证](../../Doc/加速器形式验证_20261108.md)。
v1服务器实测29秒收集完成，实际FM停在read_reference：`TpuPkg.sv`首行package触发
FMR_VLOG-481，尚未match/verify；ICC2文档会话EXIT_0，原候选未变。
v2显式确认原生`read_sverilog`及其安装手册选项，用`-define {SYNTHESIS TPU_SRAM_MODEL}`
读取参考；实现网表继续使用`read_verilog -netlist`，不修改RTL/网表/库。
Windows/Linux各7项编排测试通过，普通Verilog读取器被测试替身设为拒绝参考RTL，
另检查原生SV读取失败不得进入match/verify；这些不是硬件等价测试。
旧v1入口与实际报告保留，v2服务器结果待回传。

v2实际已成功读入SV，停reference_top；原生日志确认FMR_ELAB-147仅在TpuSram.sv第37/38行：
RegionData有7项，3位选择器存在索引7，选择寄存器未复位。尚无越界不可达证明。
v3在固定源SHA与上一轮原生日志SHA一致、仅这两处消息且无其他FMR_ELAB代码时，
以`set_mismatch_message_filter -warn FMR_ELAB-147`允许继续链接和比较，不改RTL/网表，
不假定索引合法或复位状态、不豁免比较点。会保留`InterpretationReview.json`并复核新日志警告位置。
原生verify真也仅为`TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING`；数组安全仍NOT_PROVED。
Windows/Linux各8项编排测试通过，覆盖额外警告位置/编号、源变动和精确消息过滤范围。
这些是验证流程测试，不是越界不可达或硬件等价证明。v3实际服务器结果待回传。

最新v3真实结果：MATCH=1、VERIFY=0；失败点报告列出20 matched failing points、0 unmatched，
没有aborted点。可见失败集中在Matrix计数/偏移寄存器，根因仍需反例和失败锥分析。
v4保持相同设置，只在verify失败后保存原生会话/反例，再做`analyze_points -failing`及分析摘要。
每项先核对安装man，失败仍如实保留。会话仅留服务器，反例小于等于64MiB才加入归档，超限明确记录。
Windows/Linux各10项编排测试通过，旧入口不可变；v4尚未在服务器运行。

v4已实测149秒完成，FM124秒：match1/verify0，20失败、无aborted；原候选未变。
FailureSession.fss已生成，原生分析报告找到9个unmatched cone inputs，已见LastColumn[3/4]。
write_failing_patterns命令不可用，反例文件没有生成。失败比较点的matched状态与其输入锥匹配是不同统计。
下一步读取完整分析并定位原加速器SVF，验证来源后再决定处理。ICC2仍未实际导入/布局。

已列全9输入：Matrix LastColumn[3/4/7]、LastChunk[1]、ParameterColumnStride[5/8]、
Result[63/61]、BiasWordBase[13]；另有16 Required Inputs，不能将其算为新增失败点。
原shared_asic目录找到default.svf。v5从材料记录追溯原目录，核对冻结candidate.v、16源及两库SHA，
唯一SVF复制后绑定SHA；同目录关联不是历史SVF内容证明。设计读取前set_svf，自动setup关闭，
输出指导摘要及真实verify结果。所有输入复查，未改变RTL/网表/状态假设/比较点。
Windows/Linux各12流程测试通过，上传器formal已指v5，服务器实际结果尚待回传。
