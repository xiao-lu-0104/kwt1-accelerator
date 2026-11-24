# 2026-11-07 系统任务活动与功耗进度

## 2026-11-08：标准库数值重放与完整参数补入实际通过

服务器目录`~/soc/tpusoc_numerical_replay_20261107_HzgHGV`（以原输出为准），57秒exit0。
15组FF1、12层编码器全部通过；37份参数/输入/输出/manifest补入且SHA匹配；旧候选包保持不变。
新`InitialMaterials.candidate.tar.gz`79,965,823B，SHA256
`63104eac90eb30e02dd1f8df504fea4360fbdb8a73fb8945ebb222ee1186bbda`。
当前初赛原始材料主包已汇总数值与后端证据。无需再为本阶段安装NumPy或重复执行。
这是标准库定点翻译/冻结HEX检查，非原NumPy浮点转换执行或官方600样本精度成绩。
最终报告、功耗默认/X及固定外设边界、完整RTL/EDA复现入口和提交渠道继续核对。

## v3候选包已生成，标准库数值重放补充入口

服务器实际目录 `~/soc/tpusoc_initial_materials_20261107_K52Fc0`（以原输出为准），
合并38秒exit0，86份HEX同版核对PASS，后端原件不变。
`InitialMaterials.candidate.tar.gz`为76,181,682B，SHA256
`5d44fec1b2e8a02861e2acd8c0ec4f36ea47d562b13331cca3ce8c2a553c7224`。
服务器模型重放是`DEPENDENCY_UNAVAILABLE`，不能记成执行通过。

新增`CheckSharedHexScalar.py`标准库定点翻译，绑定原Reference SHA；本地15组FF1、12层编码器HEX全部通过。
原NumPy模型保持，逐算子/阶段对照与原件保护检查见[补充入口说明](../../Doc/数值重放补充_20261107.md)。
新恢复入口通过FTP送入完整3.8MB数值归档，并恢复37份原参数/输入/输出/manifest及SHA；不安装服务器软件。
新候选包保留旧依赖缺失记录，原候选包不变；服务器执行尚待用户运行。

## 下一阶段：服务器内合并数值源码与后端材料

实际传输更新：用户回传v3入口117819B上传第1次成功，FTP226、curl exit0、sent117819。
上传脚本已将`bash ~/Desktop/tpusoc_initial_materials_20261107_v3.sh`放入用户本机剪贴板。
这证明脚本已传到服务器Desktop，尚未收到远端执行结果；合并候选包仍不能标为已生成。

用户要求不下载服务器文件，提交渠道待确认。新增 `MakeInitialMaterials.py`/`InitialMaterials.py`，
以原后端归档SHA和归档内部manifest绑定目录原件，逐文件校验后合并数值源码与当前报告。
输入数值源来自已验证的本地归档d6d63bb158523bb3423c735f6d793a54e613c29b4bd29c253ca3a7656ffb3b1b；
对照原源码manifest和服务器86份HEX，不发送3.8MB浮点参数数据，只登记来源和SHA。
`CheckSharedHex.py`调用原数值Reference，15组FF1/12层编码器本地逐值重放已通过；
`CheckInitialMaterials.py`支持移动后的完整性和模型重放检查，不会在包内写输出或安装工具。
缺NumPy会明确记录未执行，不误报通过；黄金被改、原件清单与归档不符时拒绝完成。
服务器运行尚待执行，候选包不能提前标成已生成或完整RTL/EDA复现通过。

## 后端原始材料已实际归档

服务器收集53秒exit0，`RESULT: BACKEND_RAW_MATERIALS_PACKAGED`。
目录 `~/soc/tpusoc_backend_materials_20261107_OSQ1gA`（目录拼写以服务器原输出为准）。
`BackendRawMaterials.partial.tar.gz`：73,844,357B，SHA256
`0c4d86a28160769abeaedfcc832368723dbbcb61509767f716f86aabfd390fe3`。
旁文件 `BackendRawMaterials.sha256`。下文归档“尚待执行”为历史状态，现已完成。

源码、修订固件、网表、SDC、面积/时序、两任务SAIF/严格验证日志与功耗已收集；
默认/X活动及预布局/外设边界限制随包保留，不代表最终提交验收。
两任务区域用户标注+传播：CPUcore nets91.2830%/pins88.1324%，加速器99.8512%/99.5849%，
共享TCM45.2580%/50.5060%。默认nets/pins分别1316/6521、112/1232、1114/4059。
对象数量覆盖并非功耗误差界；剩余X为FF1 9876/encoder 11430条，无全局豁免。
接下来下载备份、合并数值模型包、核对报告/版本清单与干净复现入口。

## 最新实测：启用映射后的自动匹配成功，后端材料归档入口已备

实际目录 `~/soc/tpusoc_system_power_auto_active_20261107_EQ6eDI`（以服务器原输出为准）。
FF1 DC112秒、encoder DC110秒、summary15秒均exit0，SAIF_MAPPING_ACTIVE_BEFORE_DDC确认，最终AUTO_NAME_MATCHED_SYSTEM_POWER_COMPLETE。

| 任务 | 动态/mW | 泄漏/mW | 总功耗/mW | 能量/µJ |
|---|---:|---:|---:|---:|
| FF1 | 33.8795 | 0.3817452 | 34.2612452 | 75.9162082 |
| encoder | 32.3216 | 0.3819243 | 32.7035243 | 323.937846 |

FF1总数由动态+泄漏复核，先前口头读成34.261452是抄读错误，已更正；正式包从实际JSON取数。
SRAM总mW：FF1私有4.01269/ITCM3.9994/DTCM4.6734；encoder3.42769/3.8104/4.1834。
相比首版分别变化+0.0408002mW和+0.004mW，不以小变化直接证明所有默认/X无影响。

两任务全局计数相同：
- nets93644，user81360（86.88%）、propagated9356（9.99%）、default2928（3.13%）；user+prop精确96.8732647%。
- pins365025，user323591（88.65%）、propagated28263（7.74%）、default13171（3.61%）；user+prop精确96.3917540%。
- ports971，全user。
传播是工具从已有活动推算，不能算直接仿真；用户标注中仍可能含TX，不能叫全部已知活动；对象数量覆盖不是功耗误差界。
区域直接用户标注：CPUcore nets15097/37.01%、pins54948/43.03%；加速器nets75288/99.85%、pins296781/99.58%；共享TCMnets2035/11.79%、pins8201/19.89%。
这些区域数据仍需计入propagated，归档入口从JSON直接计算完整区域user/prop/default分项。
剩余默认/X无全局豁免，外部固定外设边界和TT预布局条件保留；原始估算报告现已取得，不继续盲换标注选项。

后端归档入口 `tpusoc_backend_materials_20261107_v2.sh`，34713B，SHA256
`7e664d4ab03e614cfd4008a04998bacf8a838679f4e6cadbf3e60a31a38e0606`，paste17572B。
只读校验/复制/打包，无DC/综合/仿真；输出BackendRawMaterials.partial.tar.gz及SHA。
包括修订boot与实际任务FW、网表/修正SDC、面积时序功耗原报告、两份SAIF/严格验证日志及默认/X限制。
包内Sources/Team仅新包中覆盖为修订FW，原bundle保持；原manifest和旧原件档案置于Provenance/LegacyEvidence。
实际仿真HDL取自bootfix记录的original_task_run，避免复用simv的新任务目录并无这些HDL。
外部foundry库不复制；包保留适用范围、初始种子、预布局、外设边界和数值样本证据缺口，不称最终提交或干净portable复现。
3项Windows和Linux3项、Bash及载荷SHA通过；服务器归档尚待用户执行。

## 最新实测与修复：自动映射机制未启用（脚本遗漏）

用户实际auto目录P0AeRb（以服务器原路径为准）：prepare29秒成功、auto_power_ff1 20秒exit1。
真实报错PWR-604 `The SAIF name mapping mechanism is not active`，随后PWR-634无法创建自动map，故未标注。
这次明确缺少映射机制启用步骤，是执行脚本遗漏；功能黄金与已有首版功耗原件不变。
此前原生map-only的PWR-362是否完全同因尚未实测证明，保留失败记录，不写成已证实根因。

修复：SystemPower.tcl在read_ddc之前执行saif_map -start，显式检查失败并输出SAIF_MAPPING_ACTIVE_BEFORE_DDC。
tool_status保存NAME_MAPPING_LIFECYCLE: STARTED_BEFORE_DDC；本轮自动匹配汇总要求该证据，缺失即拒绝。
新入口 `tpusoc_system_power_auto_20261107_v2.sh`，94587B，SHA256
`8df1dae41ca92830cbc3d8821f785604d3f8f4e7d6f0de070e89913d2c8491bd`，paste38048B。
新namespace power_auto_active_20261107，原DDC/已通过的两份SAIF不变，无仿真或综合、无原生map加载或活动覆盖。
本地Tcl接口测试补充生命周期约束：去掉启用段触发PWR-604，启用失败或在DDC导入之后启用均拒绝；补上顺序后协议测试通过。
Python额外检查缺生命周期证据不能生成完成摘要。Linux4项、Bash/载荷SHA通过。
这是本地接口与传输验证，不能代替服务器DC真实成功；服务器v2待执行。

## 最新实测：原生map-only标注失败，独立自动名称匹配入口已备

实际 `~/soc/tpusoc_system_power_mapped_20261107_2bfThf`：prepare9秒exit0，FF1 DC19秒exit1。
已读原生映射PWR-637和SYSTEM_NAME_MAP_LOADED，但read_saif -map_names报 `PWR-362 No switching activity has been annotated`。
尚无映射后的新功耗；encoder未运行。两项任务功能与原SAIF/原首版功耗报告仍保持有效。
这说明这次原生map-only调用对当前SAIF没有任何匹配；具体映射语义/层级原因待已安装手册定义和对照结果确认，不能预先宣布根因已修。

新入口 `tpusoc_system_power_auto_20261107_v1.sh`，93774B，SHA256
`d4db96a70e5c480ac80db12dd72f8cbe66602ebe8a3d29e55bd056a9035b9578`，paste37752B。
新目录 `tpusoc_system_power_auto_20261107_XXXXXX`，新DC会话明确不加载原生map，使用手册已确认存在的-auto_map_names。
原DDC/两份已通过SAIF、库和SDC不变，保留前次失败尝试，无仿真/综合或活动覆盖。
本轮额外保存/打印installed read_saif的instance_name、map_names、auto_map_names定义段，避免仅凭语法列表解释语义。
全层级统计和前后比较继续保留；可选输出CPUcore/加速器/共享TCM区域覆盖，定位剩余标注缺口。
未知态、默认活动仍未豁免；自动匹配是否提升覆盖必须看服务器实际结果。
本地相关Python/Tcl及Linux对照测试、Bash/载荷SHA通过。服务器此入口尚待用户执行。

## 最新实测：全层级覆盖已明确，原生映射功耗入口已备

只读审查 `~/soc/tpusoc_system_power_review_20261107_YQFY3q` 实际67秒完成。
每个覆盖报告只有一张表，因此此次695nets/16pins的根因是默认report_saif只报顶层，**不是已经触发多表覆盖**；此前修复的多表覆盖保护仍保留。
实际 `report_saif -hierarchy` 与 `-hierarchy -missing` 均统计93644nets、365025pins、971ports。
两任务全层级user net=86.86%、user pin=88.62%，不能以默认顶层99.86%充当系统覆盖。

综合生成 `system_name_map.tcl` 实际10425458B，原生头部：
`SAIF name mapping file`、`created using Synopsys Power Compiler T-2022.03-SP5-5`、`design e203_cpu_top`、`port inspect_pc[31]`、`oname Bs:inspect_pc Bd:31 L:inspect_pc[31]`。
这是原生映射数据文件，后缀不代表可执行Tcl；不可用source加载。
真实installed manual确认read_saif支持-map_names/-auto_map_names，saif_map支持-read_map；help仅给命令名称，早先用help检索选项造成未启用自动名称匹配。

下一入口 `tpusoc_system_power_mapped_20261107_v1.sh`，89706B，SHA256
`f7955d5e3d97050665e44e4fc0848be0375f388267ef58032aa0efbe72c7a1d8`，paste36390B。
独立目录 `tpusoc_system_power_mapped_20261107_XXXXXX`，校验原L4HT7n输入和报告manifest，复用已通过的两项系统SAIF及原系统DDC/库/映射。
用 `saif_map -read_map` 读取原生文件，再 `read_saif -map_names` 标注；失败即停止，不悄悄回退成原直接标注。
无仿真/综合/硬件或活动人为修改，原功耗与黄金证据保持。
强制全层级覆盖报告；顶层统计独立保存；比较前后对象总数、user/default/propagated数量与功耗差异。
`MappedPowerComparison.json` 纳入原始报告归档，仍不豁免未知态或默认活动。
Windows6项相关测试、Linux2项、Bash和载荷SHA通过；服务器该入口尚未运行。

## 最新实测：系统范围功耗首版报告已生成

实际服务器 `~/soc/tpusoc_system_power_20261107_L4HT7n`。
prepare38秒、FF1 DC31秒、encoder DC32秒、汇总7秒，均exit0；报告/宏数量/SDC/叶签名核验已通过，`SystemPowerReports.partial.tar.gz`已生成。

| 任务 | 动态/mW | 泄漏/mW | 总功耗/mW | 任务能量/µJ |
|---|---:|---:|---:|---:|
| FF1 | 33.8387 | 0.381745 | 34.220445 | 75.825803 |
| encoder | 32.3176 | 0.3819243 | 32.6995243 | 323.898224 |

SRAM组总功耗mW：FF1私有4.01269、ITCM3.9614、DTCM4.6714；encoder私有3.42769、ITCM3.7994、DTCM4.1894。
范围e203_cpu_top，含CPU/内部ICB/加速器/私有56宏/共享64宏，外部固定平台仍需边界审查。
实际工具方法 `DIRECT_HIERARCHY_NAME_MATCH`，当前help文本未匹配-auto_map_names，外部system_name_map.tcl未source。
这些数值是已输出的TT预布局首轮带活动估算，不是最终验收功耗。

摘要覆盖显示两任务相同：nets总695/user694/default1，pins总16/user14/default2，ports总971/user971。
这不能直接当作完整系统门级覆盖率。代码核对发现v1汇总遇多张表会后表覆盖前表，已修复保留每表与上下文，并拒绝未经明确层级选择的多表。
尚未看到实际原报告上下文，不能预先断言是多表覆盖还是报告本身局部统计；更不能以局部99.86%宣称完整系统已标注。

只读审查入口 `tpusoc_system_power_review_20261107_v1.sh`，23254B，SHA256
`c303d144dec6e3e1a9687301a42b0537d2535269efefb3b947f9bb35191c6092`。
读取完成run的saif_coverage/saif_hierarchy/saif_missing每表与上下文、原始未知信号分块、综合生成name map命令样例及已安装read_saif/saif_map帮助手册。
独立namespace保存SystemPowerReview.json，manifest和输入SHA证明原功耗/报告/SAIF不变，不重跑DC/仿真/综合。
Windows6项相关测试、Linux2项、Bash和粘贴SHA往返通过；服务器该审查入口尚待执行。
下一步依实际全层级覆盖与名称映射格式决定是否需补CPU RTL到门级映射，原始未知态尚无功耗豁免。

## 最新实测：boot修复后两项服务器严格任务通过

用户服务器运行 `~/soc/tpusoc_boot_gpr_fix_20261107_L9VCpP`，新固件同配置复用原simv。

| 任务 | 实际仿真耗时 | 黄金值数 | 任务周期 | 系统SAIF时长/s | SAIF字节 | 非零TX记录 |
|---|---:|---:|---:|---:|---:|---:|
| encoder | 1879秒 | 6336 | 1485719 | 0.009905288573 | 22209635 | 11430 |
| FF1 | 525秒 | 25344 | 332354 | 0.002215804118 | 21663977 | 9876 |

encoder DMA读112256B/写12672B/装载112264B，FF1读45952B/写50688B/装载45960B，均与原任务要求相同。
每项全容量物理TCM初始化/读回/释放、严格黄金、原pattern2释放检查及new_control_QX=0通过。
共享宏输入/实际写入位/读后Q已知检查通过：encoder reads3512312/writes62510，FF1 reads784524/writes48324。
两项SAIF TX_records=130573，TZ_nonzero=0，maxTX_fraction=1；实际周期/SAIF窗口校验通过。
最终 `RESULT: BOOT_GPR_FIX_TASK_ACTIVITY_COMPLETE`，不是退出码推断的成功。
启动GPR缺失导致的有效X写入已修复；未将其他idle/模型内部SAIF未知记录判为无害。
后续功耗必须使用本次新FW SAIF和实际周期，不能混入旧固件或本地两态对照的周期/SAIF。

## 下一入口：已有系统检查点的带活动功耗报告

`tpusoc_system_power_20261107_v1.sh`，81943B，SHA256
`357f9e9ae6642d071457c16a438578f34d8b5b83360c1b306533e8746743f1f5`，手动paste34039B。
自动选择完成的bootfix两任务摘要，先验证原件SHA、SAIF窗口和全部原始TX计数。
独立输出 `~/soc/tpusoc_system_power_20261107_XXXXXX`，只读DC，无重跑仿真/综合或活动人为覆盖。
输入为原系统candidate.ddc及真实std/private/shared库，重施已核验的两转发时钟角色并要求序列化SDC与原验收视图一致。
整机标注范围SharedTest/Cpu；强制56private+32ITCM+32DTCM，并保留叶单元签名不变。
输出top功耗、三个SRAM分组功耗、全SAIF覆盖/default数量、原始未知对象列表、系统功耗摘要与原报告归档。
综合生成的system_name_map.tcl保留为独立证据；首轮仅用当前installed read_saif名称匹配（help证实支持时加-auto_map_names）。
若CPU RTL到门级映射覆盖不足，再依据实际覆盖和生成映射补充；不能把未标注对象视为已标注或零功耗。
4项本地测试通过，包含Tcl失败/错宏数反例、单位与SRAM账目、覆盖计数、端到端旧原件保持/变更拒绝；Linux导入/Bash/粘贴SHA往返通过。
服务器此入口尚未运行，无系统功耗数字。结果标签保留coverage/X/宏模型和外部固定平台边界审查，不是最终功耗验收。

## 最新：运行时确认启动GPR未初始化压栈；boot修复入口已备

用户实测诊断目录 `~/soc/tpusoc_encoder_write_trace_20261107_v2tZGE`：准备8秒、编译58秒、复现29秒、汇总12秒。
`CPU_DTCM_WRITE cs=1 we=1 wem=f din=xxxxxxxx byte_address=9003fff8`；
`CPU_GPRS sp=9003ffa0 s0=xxxxxxxx`；宏62的A=ffe/WEN=0000/D=xxxx。
fetch_pc=800000fc，冻结反汇编前一条800000fa是 `sw s0,88(sp)`，地址完全对应。
本次不是算子算错的已知证据，而是原boot未初始化无复位CPU寄存器后由C函数保存旧值。

当前 `Sw/SharedStart.S` 在原boot前增加31条正常RV32I指令，清零x1..x31；原sp/mtvec/data/bss设置及C入口全部保留。
无RTL或任务算法变化，无任务期间force，无X检查豁免。冻结bundle保留原字节。
从冻结源码重建原bin和完整HEX，与原件逐字节一致；新固件机器码逐条校验31个寄存器初始化，内存布局/任务源代码相同。
构建材料 `workspace/Checks/BootGprFix_20261107_v1/fixed`：源码、链接脚本、ELF/bin/HEX/反汇编、Compiler.txt及BootFix.json。

本地已存在CPU对照Verilator仿真器换用新固件，严格黄金结果：
- encoder 6336值，1485674周期，DMA读112256B/写12672B、装载112264B。
- FF1 25344值，332247周期，DMA读45952B/写50688B、装载45960B。
这是两态CPU RTL本地对照，不能代替服务器四态门级加速器+真实宏的X保护通过证明。
指令/对齐变动使本地测得周期与旧固件不同，保留真实计数，不伪造为旧基线。

入口 `tpusoc_boot_gpr_fix_20261107_v1.sh`，50198B，SHA256
`f107cc1e66666eb07fb7112d4f1cfa4e44da5789777f1929bc8b1cca9b627acc`。
新目录 `~/soc/tpusoc_boot_gpr_fix_20261107_XXXXXX`，复用ZBysEH原simv和所有原guard/原始任务向量，上传独立修订固件。
先encoder再FF1，两个任务用同一新固件重新采集系统SAIF；旧FF1和失败encoder原件保持并校验哈希。
准备核对远程原FW与本地重建原FW、全部冻结固件源码/布局，以及本次修订镜像机器码/SHA。
10项Python测试、Bash语法、粘贴载荷SHA往返通过；服务器尚待用户执行。
预计30–60分钟受服务器速度影响；encoder45分钟/FF120分钟为阶段限额，不是耗时承诺。
系统DDC功耗仍未执行；仅双任务及新SAIF通过后才能继续标注和覆盖/X审查。

## 物理TCM系统任务首次运行

用户实际run：`~/soc/tpusoc_system_tasks_20261106_ZBysEH`。
准备23秒、VCS编译57秒，均exit0；FF1仿真582秒exit0。
原CPU RTL/原控制器+冻结映射加速器+真实宏功能模型，不冒充全系统门级/SDF验证。

FF1实际通过：
- ITCM写入32768字、DTCM写入65536字，全容量读回分别32768/65536；所有初始化驱动在CPU复位释放前撤除。
- 25344个数值严格黄金比较PASS，任务332348周期，与原行为TCM基线一致。
- DMA读45952B、写50688B、host装载45960B；原计数/边界断言保留。
- 共享宏保护PASS，聚合reads=784506、writes=48324，活动输入和读后Q均已知。
- 原pattern2初始化释放/检查PASS，new_control_QX=0；其他必需守卫已通过，验证器执行到了SAIF头部解析。
- 任务活动窗口duration_ns=2215764.116，start_ns=1211753.918，end_ns=3427518.034。

末尾Python验证6秒后失败：`Missing SAIF duration/unit`。
旧解析器只接收整数DURATION及普通小数TIMESCALE，未兼容科学计数形式。
目前未看到真实头部两行，不能断言具体哪个字段用了指数；续跑入口会打印原TIMESCALE/DURATION。
FF1功能结果已获得，原SAIF保留待新解析校验；encoder因前一步停止，尚未启动。
系统DDC活动标注、功耗与覆盖/X审查尚未执行，无系统功耗数字可报告。

## 只续跑缺失阶段的入口

`tpusoc_system_tasks_resume_20261107_v1.sh`，32469B，SHA256
`94df2dbee7da1b9263f6a374768e083c159a6677cd11872203a3b94ef5f9719d`。
固定复用ZBysEH原simv及FF1 run.log/task.saif，不改旧输入清单/HDL/编译产物，不重编译、不重跑FF1。
Decimal解析标准SAIF数值（整数/小数/科学计数）和fs—s单位，仍严查正值、唯一头部、周期窗口误差≤2ps。
先保存实际头部及FF1 Activity.json并冻结原输入/二进制/FF1原件；只运行缺失encoder。
最后验证encoder并写独立resume/SystemActivitySummary.json，记录两任务原始证据SHA与FF1原件保持。

7项本地测试及Linux2项新增解析/续跑集成测试通过：
各种数值格式、零值/负值/NaN/重复头拒绝、保持二进制/FF1字节、禁止无encoder完成证据就生成总摘要。
Bash语法与手动粘贴载荷SHA往返核验通过。服务器续跑尚待执行；30分钟encoder限额不是耗时承诺。
未来完整生成器版本升为20261107_v2；已部署v1原字节保留。


## 续跑实际结果：FF1系统SAIF已验证，encoder缺少黄金完成证据

用户运行 `ZBysEH/resume_20261107_Gkte0A`（目录以服务器实际输出为准）。
FF1校验19秒exit0；真实SAIF头为`(TIMESCALE 1 ps)`、`(DURATION 2215764116.00)`。
前次失败的具体原因是DURATION带小数`.00`，不是已确认的科学计数；Decimal修复已实际通过。
FF1系统SAIF约21,666,147字节，TX_entries=130573，TX_nonzero_entries=10644，TZ_nonzero_entries=0，max_TX_fraction=1。
黄金332348周期、时长0.002215764116秒和原结果一致；未知态活动保留，未作功耗豁免。
encoder进程30秒exit0，终端仅见物理初始化PASS和INIT_FINAL；无PASS SHARED、TASK_ACTIVITY_END或共享宏任务守卫完成。
最终校验12秒后正确拒绝`Missing strict golden and DMA result: encoder`。
不能把退出码0或初始化PASS当作encoder黄金验证成功，也不能预先归因为汇总格式错误。
尚未看到encoder/run.log尾部的具体退出原因；下一步只读取该现存日志，定位后再决定修复，暂不重跑。
FF1现有数据与原编译产物保留；完整双任务摘要/encoder系统SAIF与系统功耗仍未完成。


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
