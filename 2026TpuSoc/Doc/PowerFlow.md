# 当前候选的功耗与面积收尾

先冻结已通过三种 FF1 初态和单层编码器的原候选，
保持同一网表、库、频率、任务向量及初始化政策，避免将不同配置的 PPA 拼接。

## 统计边界

赛题指南第 12 页要求系统任务功耗包含 E203、加速器、互连及 SRAM；
第 13 页的面积预算则只计新增加速器/接口/内部 SRAM，复用平台单列。
所以当前候选的加速器功耗是分项，不能直接作为竞赛系统总功耗或能耗。
CPU/互连/共享 SRAM 的估算范围及模型来源仍需补齐，不按零处理。

## 第一入口：短预检查

`Server/SharedAsic/MakePowerPreflight.py` 生成 `tpusoc_power_preflight_20261105_v2.sh`。
v1 在服务器因不支持 `report_environment` 中断；v2 去掉该命令，
可选帮助/库文档导出失败只记录原因，链接、时钟、宏数量、面积校验仍严格执行。
这个入口只完成：

- 核对已通过的四项门级任务、原候选和 DDC、原始 TT 标准单元及私有 SRAM DB 的关联与哈希。
- 读取 checkpoint，不重新综合、不修复 hold、不改原网表或约束；保存实际工具命令帮助、
  库单位、叶面积与使用的库引用，确认 56 个私有宏和原 150 MHz 时钟。
- 将使用的全部库引用与同版 LEF 的 SIZE 比较。任何缺失或不一致均保留“物理单位待核验”。
- 检查提供的原始 Liberty 是否包含 internal/leakage power 数据，记录模型校验值，
  列出可用 SRAM 包和当前平台内存源文件，供补齐系统功耗边界。
- 只对四个实际 DQV0 单元运行 32 个计数周期的原生 SAIF 小测试，核验 320 ns 活动窗口及非零翻转计数。
  这不是完整任务活动，也不产生最终功耗数字或确认 Power Compiler 实际授权可用。

输出的 `summary.txt`、`units.rpt`、`help/`、`Geometry.json`、`LibraryEvidence.json`、
`SystemMemoryCatalog.json`、`PowerInputs.json` 和小 SAIF 均保留在独立服务器目录。

## 后续步骤

服务器 v2 预检查 `tpusoc_power_preflight_20261105_zMTI4Q` 已完成：
126/126 已用引用全部匹配 LEF，合计 0.703272383 mm²，其中私有 SRAM 0.512317367 mm²；
这是单元/宏占地之和。真实单元的原生 SAIF 小测试 320 ns 通过，命令存在，尚无任务功耗值。

第二入口 `tpusoc_task_power_20261105_v1.sh` 自动追溯上述成功记录，
仅在原严格 testbench 的计时起点和最后输出响应处加入被动观察调用，
复用原 pattern2 一拍复位初值及释放、镜像、黄金结果和 X 检查。
依次运行完整 FF1/单层编码器后，以原 DDC 标注 SAIF，读取功耗和覆盖报告，
保存 56 个私有 SRAM 的逐单元功耗报告。完整 SoC 功耗仍待补 CPU/互连/共享 SRAM。

活动从第一笔输入请求所在下降沿开始，到最后输出响应后下降沿结束，
覆盖整数个完整计数周期；窗口含输入/参数装载和全部总线等待，排除初始化/结果比较。
实际 testbench 时钟为 6.667 ns，约束为 6.666667 ns；两者都显式记录，不静默重标定活动。
完整任务使用 SAIF 的 1 ps 时间单位以保留窗口精度；估算能耗使用 SAIF 实际时长。
默认功耗报告的数值只在其显式带 W/mW/uW/nW/pW 时解析，不能用 report_units 的 N/A 猜单位。
TX/TZ 未知活动和缺失标注保留待审，不将未标注范围按零计入；零延迟活动亦不代表 SDF 毛刺功耗。

完整任务入口已在服务器 `tpusoc_task_power_20261105_M9kwn1` 完成。
FF1/单层分项约 23.2008/22.3536 mW、51.4075/221.4175 µJ，
完整功能与窗口再次核验通过；CPU/固定互连/共享 SRAM 不在这两个数值中。
层级网线/引脚标注 99.85%/99.58%，112 网线/1232 引脚仍默认活动，
两处活动冲突及 TX 非零对象需先复核。只读 review 入口复用现有 SAIF/报告进行分类，不重跑仿真。

2026-11-06 的 review v2 已完成：两个显式注释被正确处理，TX 全量计数一致。
实际 missing 清单为零，安装手册说明其中排除常量连接；默认比例本身不能视为漏标比例。
但仍有 309 个源 SAIF 对象在 DDC 中未找到，未知 NET 的实际驱动/负载及活动冲突尚需核查。
下一入口 `tpusoc_activity_objects_20261106_v1.sh` 只读原 DDC 和 SAIF 做精确对象查询，
并冻结平台源码和共享宏接口证据；不重新综合、仿真或设置替代翻转率。

预检查确认已安装命令及 SAIF 流程后，给完整 FF1 和单层任务增加被动活动采集，
任务起点与最后写响应窗口需对齐；初始化、程序装载与结果比较不进入活动窗口。
完整任务仍需黄金结果和严格 X 检查通过，再用保存的候选做功耗估算，
检查 SAIF 标注/缺失范围及全部 SRAM 模型，分列内部动态、净开关和漏电功耗。
未标注的逻辑不能自动按零活动处理。

对系统功耗另补 E203/互连与平台共享 SRAM 的模型及活动依据，
共享存储当前使用平台仿真模型，不能自动当作已做物理宏功耗建模。
若采用分项补算，需公开宏模型、访问/时钟活动、负载假设、缺失覆盖与误差限制。
系统范围齐全后再计算平均功耗与单任务能耗，不把加速器分项当作总值。

## 方法依据

Synopsys 说明 SAIF 携带静态概率及翻转率，供功耗工具使用；
这些统计不能代替输入向量本身或保证重建相同内部状态，
因此这里优先对实际门级任务采集活动并检查映射覆盖。
参见 [Synopsys：From RTL to Gate-Level, Optimize Your Power Profile](https://www.synopsys.com/articles/understanding-power-profile.html)。
Power Compiler 的工具范围参见 [原厂数据表](https://www.synopsys.com/content/dam/synopsys/implementation%26signoff/datasheets/power-compiler-ds.pdf)。

VCS 原生 SAIF 及库单元监测参数的依据为 Synopsys《VCS/VCSi User Guide》SAIF Support 章，
[高校保存的原厂手册](https://users.ece.utexas.edu/~patt/10s.382N/handouts/vcs.pdf)。
实际 2020.03 VCS 和 2022.03 DC 的可用性仍以服务器自检及内置帮助为准；
不为旧版手册与已安装工具的差异编造通过记录。

SAIF 层级映射和逐单元功耗命令另参考 Synopsys 原厂
[Power Compiler User Guide（高校存档）](https://users.ece.utexas.edu/~mcdermot/vlsi1/VLSI2_SP_2017/synopsys/doc/POWER_Compiler/pwr_cmplr_usr_gd.pdf)。
使用显式 `-instance_name` 对齐被采集网表的层级；实际工具错误保留并阻止该分项被认定估算成功。

2026-11-06 的实际连接短摘要显示，FF1/单层有2497/4051条含X网线连接实际叶负载。
新 `tpusoc_activity_qualification_20261106_v1.sh` 沿用原网表、激励、初态、计时边界和黄金检查，
用被动观察器区分 Dot/偏置/DMA 有效消费与空闲X，检查真正启用的私有宏输入，
并对共享4096×16宏做隔离掩码和读回测试。无新综合或功耗数字声明。
原时钟辅助查询误用了当前DC不支持的PrimeTime选项；现改为
`get_switching_activity object_list`，符合
[Synopsys Power Compiler User Guide Q-2019.12 原厂手册存档](https://studylib.net/doc/28091346/power-compiler-user-guide-2019.12)
“Retrieving Switching Activity on a Pin or Net”及命令附录，仍以实际安装版本运行结果为准。
有效消费检查通过不能量化空闲组合逻辑的X功耗偏差；不能据此自动验收旧功耗结果。
