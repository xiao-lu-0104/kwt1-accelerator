# 当前平台 CPU/共享 TCM 后端与原始材料收尾

最新：initial_materials_v3服务器合并38秒成功，76,181,682B候选包已生成；服务器缺NumPy，模型重放未执行。
下一入口`tpusoc_numerical_replay_20261107_v1.sh`为5,098,608B，通过FTP上传，禁止长粘贴。
SHA256 `f1cbe937a4696c608438d9c173c13fde3da32a2d8312993f7541cc46c3e084a6`。
本机`UploadInitialMaterials.ps1 -Stage replay`上传后，服务器运行
`bash ~/Desktop/tpusoc_numerical_replay_20261107_v1.sh`。
入口以标准库翻译重放15FF1+12层HEX，恢复完整数值材料37份参数/输入/输出/manifest；原NumPy源和旧候选保持。
Windows和Linux各5项算子/阶段/错误拒绝、各3项恢复测试，以及两平台无site-packages实际全向量重放均通过。
服务器新入口尚待执行。详见[补充说明](../../Doc/数值重放补充_20261107.md)。

下一入口：`MakeInitialMaterials.py`生成`tpusoc_initial_materials_20261107_v3.sh`，117819B，
SHA256 `6f75a41cd2d267514317253cd3cc0eb5590a556e5d125b6725d21b432020b891`。
不下载服务器文件，送入原数值源码并与服务器已验证后端/86HEX合并。
15组FF1及12层编码器模型/HEX本地逐值通过；Windows5项和Linux5项测试、Bash/载荷SHA通过。
服务器执行尚待启动；缺NumPy不安装且明确未执行，功耗及最终提交限制随新候选包保留。
操作见[候选包合并说明](../../Doc/初赛候选包合并_20261107.md)。

VNC长粘贴已弃用：`.paste.txt`约10.7万字符，用户实测输入一分钟仍未完成。
改用本地`UploadInitialMaterials.ps1`通过手册允许的FTP上传v3，凭据在本机输入，
只在确认FTP226/已传字节数后提示服务器执行`bash ~/Desktop/tpusoc_initial_materials_20261107_v3.sh`。
脚本已通过PowerShell语法/CheckOnly及本地入口SHA校验；尚未认证上传，不得写成已上传。

最新实际状态（2026-11-07）：后端原始材料归档53秒exit0，`BACKEND_RAW_MATERIALS_PACKAGED`。
服务器 `~/soc/tpusoc_backend_materials_20261107_OSQ1gA`（以原输出为准）中
`BackendRawMaterials.partial.tar.gz` 为73,844,357B，另有 `BackendRawMaterials.sha256`。
SHA256：`0c4d86a28160769abeaedfcc832368723dbbcb61509767f716f86aabfd390fe3`。
两任务严格功能、SAIF、映射功耗与原始材料归档均已取得；默认/X、外设边界和最终提交检查仍未验收。
下文为各阶段历史记录，不能将早期“待执行”误作当前状态。

入口由 `MakeScript.py` 生成。只接受完成且全部通过的11月6日 qualification，
重新校验其冻结输入及原始功能/功耗来源，保留当前原CPU和256KiB+256KiB配置。

执行顺序：

1. 将已有源码包、公共平台源、原始RTL/门级功能日志、加速器候选DDC/网表/SDC、
   面积/时序报告和任务SAIF/分项功耗报告生成 `ExistingMaterials.partial.tar.gz`。
   工艺库和厂商仿真模型仅记录路径与SHA256，不拷入归档。
2. 用64个真实RAMSP4096X16建立512KiB候选组织：ITCM为8组×4个16位宏，
   DTCM为16组×2个16位宏；分别与原`sirv_sim_ram`比较合法读周期、分组边界和字节掩码。
   不比较无效写周期的旧读输出，不改变CPU/LSU/TCM控制器。
3. 转换本次私有目录的共享宏TT Liberty，使用原标准单元和私有宏DB。
4. 从原CPU顶层、候选TCM接口和逐字节冻结的加速器结构网表综合。
   约束为150MHz、setup/hold uncertainty 0.2/0.1ns、输入max/min 1/0.1ns、
   输出max/min 1/-0.1ns、负载0.035pF；所有IO（除输入时钟）均有预算，无时序切除。
   固定全部SRAM和加速器，检查56+64个宏及加速器叶单元名称/引用不变，
   最多一次CPU/外部逻辑hold修复，输出原始报告及名称映射。

该阶段不宣称完整CPU配宏TCM功能已经通过，也不宣称系统活动或功耗已经计算。
现有512KiB平台在功能仿真中仍是原行为存储；新宏接口的全CPU任务验证是后续步骤。
`e203_cpu_top`覆盖CPU、内部ICB、NICE/TPU和存储，外部固定外设不在本次映射范围。
系统全部单元面积包含CPU和共享TCM，与2.25mm²新增部分预算不同，不能混淆。

各阶段有明确wall-clock上限，`StageWatch.py`每60秒输出状态，
超时/中断仅终止自己启动的工具进程组。准备8分钟、存储编译5分钟/运行1分钟、
库转换10分钟、综合及一次hold修复40分钟。此为限额，不是实际耗时承诺。

本地验证：5项Python/Tcl接口测试、完整64/32位存储组织与原RAM的读回对照、
反转物理WEN时必须失败、工具超时和退出码保留、256KiB+256KiB本地源接口lint。
本地宏为契约fixture，Tcl为DC集合模拟，均不冒充实际服务器工艺库/映射通过。

`CheckModelMaterial.py`是独立本地原始材料检查工具，不在服务器入口中重复运行：
校验当前RTL/驱动与已通过包一致，以当前数值模型再生成完整向量，
与冻结的86份HEX逐字节比较后，归档模型、转换脚本、依赖和提取参数。
该检查不等同于官方600样本精度或分类准确率成绩。


## 2026-11-06：系统基础运行完成综合，修复汇总日志冻结缺陷

用户实际运行 `tpusoc_system_base_20261106_GamjxW`：准备/归档48秒；
ExistingMaterials.partial.tar.gz为1093个原始文件、44,253,648字节。
真实共享宏接口64/32位分别96/128项PASS，库转换exit=0。
CPU/TCM映射阶段499秒、exit=0；尚未取得最终setup/hold/面积摘要，不能据此宣布时序通过。
汇总失败原因：v1 Prepare在自身退出前冻结仍写入中的prepare.log，随后最终完成行使哈希变化。

修复入口 `workspace/Server/tpusoc_system_summary_recovery_20261106_v1.sh`，
19175B，SHA256 b85f8f58d596ee0d693ab01d8325a405c8fbdb66f54dd702bd5b2ccb7e7e0e25。
仅恢复现有运行的汇总/报告打包，不重跑EDA或仿真，不改原输入清单、网表或原始日志。
严格验证prepare.log的原冻结前缀及仅一行最终进度后缀，其余冻结输入逐项校验；
以单独RecoveryInputs记录原清单哈希和已关闭日志的完整新哈希，归档同时保留两份清单。
今后Prepare只冻结明确的静态输出；新完整运行生成器版本提升为v2，原v1保持原字节。
8项本地测试通过；Linux另跑恢复集成/前缀反例/静态输入测试3项通过，
覆盖真实汇总归档路径、拒绝其他输入变化、时序FAIL原样保留。Bash语法及传输字节往返校验通过。
服务器恢复入口尚待执行；完整CPU配宏TCM功能、系统SAIF/功耗和最终提交仍待完成。


## 2026-11-06：内部hold路径已见通过，准备时钟端口约束复核

用户第三条hold完整报告：ITCM命令FIFO qout_r_reg[77] -> ITCM宏A[0]，
arrival=0.348950ns，required=0.348867ns，slack(MET)=+0.000083ns（约0.083ps）。
报告按最差路径顺序列出，前两条为两个时钟输出的-0.2ns数据延迟误约束；
内部路径的正裕量不等于物理实现/多角通过，完整修正视图仍待工具复核。

新报告入口：tpusoc_clock_port_review_20261106_v1.sh，29652B，SHA256
f69dac1314dc9e291e0854b2349b12ada23d7805732e2d7cb376eb89c41137a7。
仅读取原candidate.ddc，在独立目录输出报告和clock_ports_corrected.sdc。
先校验已恢复输入链、系统映射manifest、原共享库和CPU时钟端口源码语义；
DC确认两输出的全扇入起点仅clk，再移除仅此两端口的数据output_delay，
建立从clk转发的divide-by-1组合generated clocks，保留输出load及原数据约束。
不compile、不插buffer、不改原网表/DDC/SDC、不加false/multicycle/min/max例外。
前后全系统leaf名称/ref一致，源文件哈希前后检查；两份SDC命令差异白名单拒绝
任何其他数据约束/根时钟预算变化；重新加载时序须与原摘要一致，再报告真实PASS/FAIL。
系统功能/功耗仍pending，未提前宣称报告运行通过。
3项Windows测试通过（含Tcl模拟正/负fan-in、禁用compile/falsepath、失败时序原样保留），
Linux另2项约束差异/汇总归档测试通过；Bash语法与粘贴载荷字节往返SHA核验通过。
命令语义依据Synopsys Synthesis Commands F-2011.09原厂手册归档：
https://studylib.net/doc/28180767/dc-synth-commands
以及Timing Constraints and Optimization P-2019.03-SP4原厂指南归档：
https://studylib.net/doc/27932205/synopsys-timing-constraints-and-optimization-user-guide-2...
最终以服务器T-2022.03-SP5-5实际工具报告为准。


## 2026-11-06：clock_port_review v1返回类型错误，v2修复并补面积分项

服务器clock_port_review_20261106_ubIos9读取原DDC成功，read_ddc返回设计列表，
v1错误按boolean判断导致退出；没有得到新的修正时序结论。原系统网表/报告未改。
已修正为read_ddc后验证get_designs中e203_cpu_top存在，本地测试返回实际类型设计列表。

新v2入口35735B，SHA256 142eaf0439cc103881c797502f638841c20de95be14dbc6be4655076081b155f。
新增AreaBreakdown.tcl按实际leaf互斥统计：加速器逻辑/接口、私有宏、CPU/内部ICB逻辑、
共享ITCM宏、共享DTCM宏、共享TCM实现逻辑、其余系统逻辑。
严格验证私有56、ITCM32、DTCM32，总和与原系统2495814.81077µm²一致；
加速器计分范围与原703272.383184µm²、私有宏512317.367184µm²一致。
这些分项是下一服务器运行应输出的证据，目前CPU独立面积/共享宏独立面积未取得。
已知非加速器合计1792542.427586µm²，不能直接记成CPU面积。
本地5项测试、Linux3项测试通过，覆盖宏数量/合计错误拒绝、逐leaf不重复、
原失败时序保留、返回设计列表以及原约束不可变化；fixture面积不是真实服务器测量。
Bash和手动粘贴字节往返SHA通过。Doc/面积分配_20261106.md列出目前实际数值及待取项。


## 2026-11-06：clock_port_review v2工具成功，修复SDC原生序列化兼容

用户实际运行clock_port_review_20261106_TiLrj3，输入核验6秒、DC报告29秒exit0。
面积分项校验与原系统/加速器合计、重新加载时序一致性均已通过，
Python最后budget_diff误拒DC原生输出：
create_generated_clock [get_ports inspect_core_clk] -name InspectCoreClock -source [get_ports clk] -combinational
其端口位置在前，且默认divide-by-1被省略；不代表约束发生非预期变化。
尚未收到修正后setup/hold数值或面积各行，不提前填入CPU/共享宏独立数值。

已改为仅解析文字、按参数语义核对源/目标/组合转发/有效分频比1，允许对象在前和省略默认1；
继续拒绝分频2、反相、来源/目标改变、数据或根时钟预算变化。
新增新时钟预算数值核对，拒绝NaN或偏离0.2/0.1/0.1的值。
只恢复汇总入口tpusoc_clock_summary_recovery_20261106_v1.sh，26877B，
SHA256 4d842c610be9d12c43cdfd48f4f5c691d6571e2ca55574407c424fbbb109f8a6。
固定现有TiLrj3目录，先打印已有area_breakdown.tsv，验证原输入并指纹化原报告，
不运行DC/综合/仿真，不改原网表/SDC/报告，只生成独立恢复清单和汇总档案。
7项Windows测试、Linux2项原生格式与恢复集成通过，覆盖所有原报告字节不变；
Bash语法与粘贴载荷往返SHA验证通过。服务器恢复尚待执行。
后续完整报告生成器版本提升v3，已有v1/v2不可变；此轮只需运行汇总恢复，不重出工具报告。


## 2026-11-06：下一步系统物理TCM任务/SAIF入口已准备

新增tpusoc_system_tasks_20261106_v1.sh，35085B，SHA256
c076fe2e229e1224cd602a85e8577470be7f236f7562151cd2e09452ae0ccbcf。
只做原CPU RTL/原TCM控制器+逐字节冻结加速器网表+真实SRAM宏功能模型的完整任务，
不把它描述成全系统门级/SDF等价证明，不综合、不在此阶段执行DC功耗。

原严格TaskSharedTest仅移除行为RAM初始化/陷阱诊断数组后门：
同一原始32768×64bit完整固件和65536×32bit DTCM零值，
在外部复位期间通过物理RAM wrapper的正常数据/地址/掩码/写使能端口写入，
全容量逐字读回，再释放全部初始化驱动；CPU/loader/测量均在此之后启动。
不force时钟，不改原CPU/TCM控制器、原黄金向量、输出比较、DMA流量或NICE计数断言。
原映射加速器pattern2一复位时钟种子/释放与ICB镜像、有效数据保护均保留。
增加64个共享宏的活动输入/实际写入位/读后Q检查；初始化过程在任务窗口之外。

SAIF范围改为SharedTest/Cpu，窗口仍为首次输入请求至最后输出响应后一完整下降沿。
原CPU/互连/私有112KiB/共享512KiB均包含于该仿真范围；读取系统DDC标注、
命名映射/活动覆盖/X审查与最终系统功耗留待得到本轮活动后继续。
保持实际6.667ns仿真周期，约束6.666667ns另列。
实际任务周期重新记录，与旧332348/1485712比较；若仅周期变化如实报告，
仍须满足原黄金值/原DMA字节数/NICE指令次数/完整时间窗口，不能沿用旧周期伪造新能耗。

准备核验TiLrj3恢复输入/报告manifest。发现此前恢复脚本manifest包含其运行中stdout日志，
后续完成行会改变该日志；新入口只对明确命名的运行日志验证原冻结前缀哈希和完整结尾，
以新清单记录已关闭完整日志，其他原报告必须逐项SHA一致。
后续ClockPortReview归档代码排除仍写入的恢复stdout日志，旧v1/v2和已归档原件不改。

本地5项Python准备/断言/窗口/日志前缀测试通过，Linux同5项通过。
原生Verilator物理macro fixture下，两种宽度完整65536/32768合法端口初始化/读回通过；
释放后普通端口新写读通过，64宏共享保护通过；故意破坏物理写掩码会读回失败。
这不代表服务器真实宏/完整任务已执行；服务器验证待用户运行。
Bash语法及粘贴载荷往返SHA核验通过。入口每60秒进度，准备5min/编译10min/
FF1 15min/encoder30min/每个结果校验3min为限额而非耗时承诺。


2026-11-07最新进度见Server/Results/20261107_SystemPower.md：ZBysEH实际物理TCM FF1黄金/初始化/守卫通过，332348周期不变；SAIF头部解析过窄导致末尾失败，encoder未启动。已准备只续跑encoder的tpusoc_system_tasks_resume_20261107_v1（SHA94df2dbee7da1b9263f6a374768e083c159a6677cd11872203a3b94ef5f9719d），保留已成功FF1和原simv，不重编译/重跑FF1。服务器续跑、系统功耗仍待执行。




## encoder原始日志明确停止原因：共享宏62写入未知位

用户提供encoder/run.log尾部：
- 物理TCM全容量初始化/读回/释放PASS，原pattern2控制状态new_control_QX=0，ICB镜像无分歧。
- TASK_ACTIVITY_BEGIN start_cycle=127763,time_ns=959001.281。
- 1706628660ps触发SharedTcmGuard.sv:568的`SHARED_MACRO_WRITE_X 62`，VCS随后$finish且返回0。
- TASK_ACTIVITY_FINAL started=1 stopped=0，effective/shared guard complete=0，未生成黄金完成证据。
因此是活动写入数据X的真实验证失败，非汇总格式，禁止放松检查或将exit0作为PASS。
Fractions.hex多余条目警告对应Layers=1只读取12条文件中的第1项，非当前fatal停止点。

宏编号32—63为DTCM，62是bank15/lane0，地址覆盖0x9003c000—0x9003fffc的低16位。
冻结原ELF静态反汇编确认：Main先sp-=96，从StackTop0x90040000到0x9003ffa0；
encoder分支0x800000fa执行`sw s0,88(sp)`，静态目标0x9003fff8（bank15/A=ffe/lane0=宏62）。
_start没有初始化s0，原CPU寄存器文件的非零GPR由无复位dffl组成。
这是未初始化callee-saved寄存器压栈的强候选原因，尚待运行时CPU地址/寄存器值确认，
不能把本地fixture中合成的同名诊断行当作服务器实际trace。
静态原ELF与反汇编依据保存workspace/Checks/EncoderWriteX_20261107。

准备被动诊断入口tpusoc_encoder_write_trace_20261107_v1.sh，20630B，SHA256
`a6120396e104d36e38a0f3127b6cc49d145e57bc809ae22b8d449377c60dea00`。
保留原FW/RTL/所有黄金和fatal守卫，加一个只读final追踪模块，输出CPU_DTCM_WRITE、MACRO62_WRITE、
CPU_GPRS、最近16个取指PC（明确是fetch_pc，不冒充提交PC）。新目录编译和复现，
不改旧编译产物/FF1原件/失败encoder日志，不重跑FF1，不输出功耗或黄金成功结论。
本地准备/不变性/缺失诊断拒绝测试和Linux同项通过，使用真实CPU RTL/物理宏层次的
Verilator lint通过；Bash及传输SHA往返检查通过。服务器诊断尚待执行。
后续若运行时证实CPU未初始化寄存器压栈，采用合法固件启动寄存器初始化并对新固件重新跑任务/活动，
不在任务内force寄存器/写数据、不给共享宏写X作豁免，不混用旧固件SAIF当新配置结果。
# 2026-11-07 boot GPR初始化修复

最新服务器auto_active_EQ6eDI两功耗报告已完成：FF134.2612452mW，encoder32.7035243mW；user+prop覆盖nets96.8733%、pins96.3918%，默认/X和外设边界限制保留。
`MakeBackendMaterials.py` 生成只读归档入口，`BackendMaterials.py` 校验原件并打包修订源码/FW、网表/修正SDC、面积时序功耗报告、两份SAIF和严格日志；旧bundle不动，包内FW明确升级；输出不是最终干净portable提交。
归档测试覆盖源bundle不变、新FW正确、原guard保留、默认活动不混为仿真覆盖、SHA和外部库不打包。

自动名称映射真实报PWR-604未激活。当前SystemPower.tcl已在read_ddc之前调用saif_map -start并记录生命周期证据，AutoMappedPower要求该证据；v2服务器入口已备。接口回归覆盖漏启用/晚启用/启用失败，服务器真实标注仍待运行。

最新全层级功耗覆盖实测：93644nets/365025pins，user net86.86%、pin88.62%；默认report_saif仅顶层695nets/16pins。
`MakeNativeMappedPower.py` 生成原生映射重算入口，`NativeMappedPower.py` 保留首版证据并比较全局覆盖/功耗。
原system_name_map.tcl为saif_map -write_map的原生数据，用saif_map -read_map加载，绝不source；随后read_saif -map_names。
全层级覆盖来源现在强制检查-hierarchy报告标题，顶层统计单独记录，前后比较JSON纳入归档。

最新服务器boot_gpr_fix_L9VCpP已通过：FF1 25344值/332354周期，encoder6336值/1485719周期，两项物理宏有效输入和读后Q保护均PASS。
`MakeSystemPower.py` 生成读取原system DDC及新SharedTest/Cpu SAIF的独立功耗入口；`SystemPower.tcl` 要求全部120个宏并保持叶签名，`SystemPower.py` 保留原始X库存、核对功耗单位/SRAM账目/覆盖和SDC、归档报告。
首轮installed read_saif名称匹配的实际覆盖必须审查，外部综合name map保留待需要时应用；不默认已实现完整RTL到门级映射。
系统功耗入口已本地测试，服务器尚待执行。

`BuildBootFirmware.sh` 从冻结bundle复现原镜像并构建boot初始化后的镜像，保留全部原任务源码/布局；`BootFirmware.py` 校验reset入口31条RV32I GPR清零指令。
`MakeBootFixTasks.py` 生成独立传输入口：复用原系统simv，先encoder再FF1，保留全部X/黄金守卫与旧结果，两任务使用相同新固件产生独立SAIF。
`TestBootFixTasks.py` 检查原件保留、固件provenance及缺失机器码反例；`TestBootFirmware.sh` 使用原本地CPU对照仿真器验证两个任务黄金结果。
本地两态对照通过不等于服务器四态X检查通过；尚无修订固件系统功耗。

