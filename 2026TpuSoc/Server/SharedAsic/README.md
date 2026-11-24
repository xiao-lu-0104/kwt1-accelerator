# 共享 SRAM 配置的新增加速器综合

此阶段综合 `Backend/e203_subsys_nice_core.sv`，与服务器共享 SRAM 十七项功能回归
使用的模块相同，包含 NICE、TPU、DMA、ICB 和 56 个私有 SRAM 宏。
CPU、512 KiB 平台 ITCM/DTCM 和外设在此面积/时序边界之外。
此阶段不能代表整个 SoC 已完成综合或功耗评估。

`MakeScript.py` 生成自包含脚本并固定已上传 shared_v1 的完整清单哈希。
运行时自动寻找原共享 SRAM 成功目录，检查十七份完整结果、每项输出/流量计数、
未改动的平台副本以及包内所有文件，再复制确实参与过功能编译的 RTL 做新综合。
不更改原平台、原功能包或历史综合目录。

使用同一 SMIC40 TT 标准单元库和已审查的 RAMSP1024X16 TT 库。
150 MHz，setup/hold uncertainty 为 0.2/0.1 ns；IO max 1 ns，输入 min 0.1 ns，
输出 min -0.1 ns，负载 0.035 库电容单位；属于明示工程预算。
包括同步 reset 在内的全部输入有约束，不切 NICE/ICB 路径。

每次保留 baseline 网表/DDC/SDC 和 setup/hold；若 hold 为负，只尝试一次
SRAM 范围的 hold 增量修复。其他层级冻结，修复前后核对时序要求及层级外单元引用。
无论时序是否达标都保留候选报告，`REPORTS_COMPLETE` 只表示工具执行完成。
报告含所有映射叶单元的库面积和 56 宏计数，单位另存 `units.rpt`，
不得把原始面积值直接写成 mm²。

本阶段不运行综合网表仿真、回标仿真或功耗估算。后续须基于该候选网表
补功能复验和完整任务活动标注，并另核对 CPU、平台存储及系统级功耗口径。
不以默认翻转率的 vectorless 数值充当实测功耗。

本地生成与检查：

```bash
python3 Server/SharedAsic/TestVerify.py
tclsh Server/SharedAsic/TestConstraints.tcl
python3 Server/SharedAsic/MakeScript.py
bash -n workspace/Server/tpusoc_shared_asic_20261105_v2.sh
```

服务器执行：

```bash
bash ~/Desktop/tpusoc_shared_asic_20261105_v2.sh
```

可选第一个参数指定原共享 SRAM 成功运行目录。日志、源码关联、库哈希、
映射候选哈希和完整报告均在独立 `~/soc/tpusoc_shared_asic_20261105_*` 目录。
v2 避免 Bash 4.2 在 `set -u` 下展开空数组的问题；v1 未交付执行命令。

## 已保存候选的只读报告恢复

v2 的一次服务器运行已完成映射和 hold 修复、保存候选，随后被层级外单元数量
变化保护拦截。使用恢复脚本读取前后 DDC 输出单元差异和时序，避免重新综合：

```bash
bash ~/Desktop/tpusoc_shared_report_20261105_v1.sh
```

自动核对原 v2 的源码/工具/库及功能关联，所有报告写到新目录。
此项不放宽保护，不修改 checkpoint，不把时序通过等同于候选已接受。
执行状态见 [当前综合记录](../Results/20261105_SharedAsic.md)。

## 候选网表功能复验

恢复报告已回传：setup +0.424492 ns、hold +0.00112969 ns，原约束未变。
候选仍需核对 37 项层级外变化及门级功能。下一入口：

```bash
bash ~/Desktop/tpusoc_shared_gate_20261105_v1.sh
```

自动查找原报告；审核全部新增单元的 Liberty 函数，并寻找原版标准单元 Verilog。
模型齐全时跑 FF1/单层的保存候选网表，保留真实 CPU/TCM 控制器。
若标准单元模型不在同版本目录，可显式设置 `TPU_STDCELL_VERILOG` 为文件或目录；
多条路径用 Linux 冒号分隔。缺少模型会输出缺失引用，不自动替代。
仿真不回标 SDF、不提供形式等价和功耗结论，完整任务功耗活动另行采集。

门级 v1 已回传：37 项全部为新增非反相 buffer，实际模型编译通过，但 FF1
回读 done 时出现输入数据字，功能尚未通过。诊断入口为：

```bash
bash ~/Desktop/tpusoc_gate_diag_20261105_v1.sh
```

它自动找失败的 gate v1，复现默认模型延迟并对比零延迟功能模式；
必要时跑同库 RTL 对照。所有候选和源码保持不变，增加被动总线事件记录。
任何零延迟结果均与原时序/计时分开，不代表已回标时序通过。

默认和零延迟门级已回传相同失败，同库原 RTL 通过；当前转入定位首个未知握手。
下一入口：

```bash
bash ~/Desktop/tpusoc_gate_probe_20261105_v1.sh
```

对比 hold 修复前/后，增加 strict 四态握手检查和被动 ICB RTL 镜像；
另跑仅替换 ICB 的诊断控制，不把该控制版本作为交付网表。
原算子 RTL、保存网表、库、CPU、参数及原测试包均不修改，不重跑综合。

probe 已回传 baseline/candidate 同处失败；混合对照未正常结束。
现先只读核对实际映射端口及顺序模型，避免对不完整镜像日志做结论：

```bash
bash ~/Desktop/tpusoc_read_probe_20261105_v1.sh
```

此脚本只运行 Python，不调用仿真器或综合器，不改动服务器文件。

片段已确认：子模块 size 端口未使用，真正的顶层 size 直接为 2'b10。
原镜像对此未使用子端口的比较为误报，已改成检查实际顶层。
实际 ready-X 失败仍待定位；现在运行小范围检查：

```bash
bash ~/Desktop/tpusoc_gate_small_20261105_v2.sh
```

包括真实触发器单元（有/无 SRAM 模型）、隔离的映射 ICB 以及修正镜像整机。
小单元仿真 20 秒、整机定位 180 秒限时，记录具体退出码和超时状态。
不改原网表，不综合，不用诊断对照替代交付版本。

small v2 已确认真实隔离 ICB 在收到两个字后控制出现 X，普通 DQV0 采样测试通过。
下一入口只运行顺序模型反馈与隔离 ICB 组合锥诊断：

```bash
bash ~/Desktop/tpusoc_gate_cone_20261105_v1.sh
```

包含实际 DFF 反馈、真实 ICB、厂商 functional 分支及独立 NBA 触发器诊断副本。
全部保留原候选与模型，不运行整机，不综合；任何替代模型结果只用于定位。
仿真每项 20 秒限时，自动打印关键 D/Q、未知组合输出及对应库模型。

cone v1 回传为反馈单元通过、三种 ICB 对照同处失败；当前读取已保存的首次 X 上下文
及完整 Word D 输入组合锥，不重复仿真：

```bash
bash ~/Desktop/tpusoc_read_cone_20261105_v1.sh
```

它自动选择指纹未变的已完成 cone 目录，打印相关真实单元功能模型及连接。

只读证据已定位 Word[0] 复位 X 悲观传播，推导见 [复位说明](../../Doc/GateReset.md)。
下一步验证该原因是否足以解释全部失败：

```bash
bash ~/Desktop/tpusoc_gate_boot_20261105_v1.sh
```

仅在一个复位时钟期间给 Word[0] 选择 0/1 初值，释放后验证复位清零；
依次运行两种初值的隔离 ICB、两种初值的完整 FF1、初值 0 的单层编码器。
原候选与实际模型不改，完整数值/严格 X 检查保留。此为明确二态初值的对照，
不将其写成全 X 初始状态自然复位通过。

boot v1 的两种初值隔离单元通过，整机在 36 次 DMA 读后仍失败。
新 `tpusoc_gate_inventory_20261105_v1.sh` 一次性枚举实际映射 FF，
记录复位 X 残留和控制寄存器已知值丢失，并比较全 0/全 1/固定随机初态的完整 FF1。
三项 FF1 都通过后才运行单层编码器；仍只在一个复位时钟施加初值后释放。
完整网表、厂商模型和严格数值/X 检查保留。

当前 FTP 服务端连接人数已满，该入口尚未上传。备用方式是在本机 PowerShell 执行：

```powershell
Get-Content 'E:\chipdesign\2026TpuSoc\workspace\Server\tpusoc_gate_inventory_20261105_v1.paste.txt' -Raw | Set-Clipboard
```

然后在服务器 VNC 终端粘贴执行。命令会解码完整脚本、核对 SHA256、保护已有不同内容的同名文件，
再执行还原入口；服务器仍需已有 Python 3、VCS 和之前完整的运行目录。

实际结果已回传：`~/soc/tpusoc_gate_inventory_20261105_fA7tXq` 中，
三种映射 FF 初态的完整 FF1 全部通过，25344 值、332348 周期；
固定随机初态的单层编码器通过，6336 值、1485712 周期。
初值均仅保持一个复位时钟，7000 ps 永久释放，ICB 镜像无分歧、无新控制 Q-X。
Word-only 参照仍 FAIL，报告须明确“指定二态初始条件下的门级功能通过”。
这不是全 X 初态自然复位、形式等价、SDF 或物理签核通过。
本轮功能结果证据已足够，下一项为同候选的任务活动与功耗估算，不重复运行本轮诊断。

功耗与报告已开始，见 [执行记录](../Results/20261105_Power.md)、
[流程与边界](../../Doc/PowerFlow.md) 及 [技术报告草稿](../../Doc/初赛技术报告_20261105_草稿.md)。
当前短预检查入口为 `tpusoc_power_preflight_20261105_v2.sh`：
只核验原候选/库、LEF 面积单位、已安装功耗命令及四个触发器的原生 SAIF 采集，
不重新综合或运行完整 FF1，不产生正式功耗数值。
v1 已在服务器因 DC 不支持 `report_environment` 停止，未运行 SAIF 小测试。
v2 删除该命令并容忍可选文档导出不可用，实际设计校验失败仍中止。

v2 已在服务器 `tpusoc_power_preflight_20261105_zMTI4Q` 通过：
126/126 已用引用全部匹配 LEF，候选单元/宏面积合计 0.703272383 mm²，原生 SAIF 小测试通过。
这不等于正式功耗已测。下一入口 `tpusoc_task_power_20261105_v1.sh`：
完整 FF1/单层任务被动活动采集、严格黄金/周期/复位条件复查、原 DDC 的 SAIF 标注与功耗估算。
原始覆盖、TX/TZ、SRAM 分项保留待审；CPU/互连/共享 SRAM 尚需补齐，不将加速器分项作系统总值。

完整任务已回传：FF1/单层分项约 23.2008/22.3536 mW、51.4075/221.4175 µJ，
DC 实际功耗计算完成，仍有默认活动、TX 和 PWR-19 冲突需要复核。
下一入口 `tpusoc_power_review_20261105_v2.sh` 只读现有 SAIF/网表/报告，
分类未知对象、打印 missing/冲突上下文和平台 SRAM 端口信息，不重跑仿真或综合。
v1 在服务器因括号表达式外文本解析失败；实际触发字符未知。
v2 支持显式注释/BOM，并增加具体位置及原文诊断；来源、TX 完整性和未知数量校验仍严格执行。

2026-11-06 v2 已实际完成，TX 数量一致，missing 清单为零（按工具规则排除常量连接）。
仍需核查 309 个未找到的 SAIF 对象、未知 NET 的负载和活动冲突。
新 `tpusoc_activity_objects_20261106_v1.sh` 只读原 DDC/SAIF 的实际连接，
并冻结竞赛平台源码和共享 SRAM 原始端口证据，不改候选、不重跑仿真、不替换活动。
系统功耗须另补 E203/互连/共享 SRAM，不能用当前加速器分项替代总值。
按用户确认，工具环境的自动剪贴板未到达本机；后续由用户在本机 PowerShell 读取
`.paste.txt` 并手动复制，再到 VNC Linux 终端粘贴执行，不能称已自动传入用户剪贴板。

2026-11-06 对象核查已实际完成。实际叶负载未知网 FF1/encoder 为2497/4051条，
时钟辅助查询使用了不支持的选项，未读到属性，不影响之前分项计算。
新 `MakeQualification.py` 打包入口执行修正后的 Power Compiler 原生查询、
原任务被动有效数据守卫和隔离的4096×16厂商宏掩码/读回测试。
它分别保留各分项状态；不把功能使用无X或宏小测试通过外推为系统功耗完成。
