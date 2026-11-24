# 单时钟 CPU＋TPU：2026-11-02

用户确认队友已提交去 CDC 版本，允许拉取并跑服务器 ASIC 150 MHz。
Git 已快进到 `88e529eff28f4ba75fc250fe2e03310e267b3af7`。
上游 RTL 与子模块保持该硬件基线；服务器适配与本地测试工具位于 Server 目录。
这些工具和当前验证记录随后整理到独立 PR 分支，原始运行包保留不覆盖。

新上游顶层是 `Backend/E203TpuBackend.sv`，CPU、NICE、TPU、AXI 共用 Clock，
统一复位同步释放。原 `Rtl/E203Tpu.sv` 仍为带 CDC 的 FPGA 顶层，不用于本次 ASIC。
E203 子模块固定 `9f3e34f337f5d0a1236a285871ffa2032491617a`；模型固定
`237e4097afd4f6851e0b82f0a8d65c2dfe8eae30`。

## 已完成的本地验证

原 CPU/TPU RTL、固件和参考向量保持不变。生成一份宿主 C++ 测试适配文件，
改用新顶层、共同 CPU/TPU 时钟、150 MHz DDR 模型配置，保留原检查逻辑与硬件断言。
使用 Verilator 5.050、上游显式 SRAM 分支、真实引脚适配层及本地 SRAM 测试替身。
未使用服务器厂商模型，本地功能通过不能代表实际宏时序通过。

| 测试 | 结果 |
|---|---|
| E203 控制单层 | PASS，1,327,674 CPU/TPU 周期 |
| E203 控制十二层，仅最终导出 | PASS，15,839,255 CPU/TPU 周期 |
| 十二层 DMA | 读 1,207,680 字节，写 12,672 字节 |
| 原 Model/CheckSoc.py | 通过，参考类别与实际类别均为 2；不代表语音准确率 |
| 单时钟约束选择测试 | PASS，Tcl mock：一个时钟、复位豁免范围、IO 预算、拒绝第二时钟 |
| 共享报表工具测试 | PASS，Tcl mock：跨组数值最差值、无效值拒绝、叶单元面积求和 |
| Bash 语法、包内哈希 | PASS |

DDR 配置为 AXI128、600 MB/s、首拍 12 周期、刷新 39/1170，保留原模型反压。
完整日志：`workspace/Checks/Backend20261102SingleClock.log`。

## 服务器交付与运行结果

源码运行包：`tpusoc_88e529e_single_20261102_v4.tar.gz`，199,498 字节。
SHA256：`4657e22732a7f3f3bb31963818170cf17f60ef95535856658db27820532c5f3a`。
已通过 FTP 上传到服务器桌面，远端文件大小确认 199,498 字节。
用户已在服务器执行以下命令并回传两个顶层的完整报告完成摘要：

```bash
mkdir -p ~/soc/tpusoc_88e529e_single_20261102_v4
tar -xzf ~/Desktop/tpusoc_88e529e_single_20261102_v4.tar.gz -C ~/soc/tpusoc_88e529e_single_20261102_v4
bash ~/soc/tpusoc_88e529e_single_20261102_v4/Server/SingleClock/Run.sh
```

入口 `Server/SingleClock/Run.sh` 默认对 TpuNiceAxi、E203TpuBackend 分别综合。
真实宏端口/文件哈希与前轮已通过验证一致，本次重新执行厂商宏测试。
56 个 RAMSP1024X16，共 112 KiB；综合前后严格检查宏数量及叶单元映射。
STA 用真实 SMIC40 TT 标准单元库和 SRAM 库，setup/hold uncertainty 0.2/0.1 ns。
不使用 CDC 例外，不修改上游 RTL，不运行全局 hold 修复。
先保存 DDC/网表/SDC，再生成报告，以便报表失败时恢复。

旧 a1d0c9a 两时钟结果仅作历史：TPU hold -0.120269 ns，CPU setup 约 +0.000703 ns，
报告脚本出现多组数值误判、设计面积属性缺失及 CDC 起止对象类型错误。
新工具统一使用数值最小值与叶单元库面积求和，不再使用 CDC 报表。

服务器运行目录：`~/soc/tpusoc_single_20261102_171803_AfUXce`（按截图转录）。
两个顶层均出现 ASIC_REPORTS_COMPLETE，最终 RESULT 为 REPORTS_COMPLETE。
截图未覆盖厂商功能测试的前段 PASS 行；本轮厂商测试详细日志仍需保留。

| 顶层 | Setup WNS（ns） | Hold WNS（ns） | 库叶单元面积总和（原始库单位） |
|---|---:|---:|---:|
| TpuNiceAxi | +0.423916 | -0.120269 | 700347.553584 |
| E203TpuBackend | +0.000449181 | -0.120269 | 726669.104784 |

56 个 RAMSP1024X16 保留，SRAM 库面积总和 512317.367184。
集成顶层按寄存器数据捕获端点分类：

| 捕获层级 | Setup WNS（ns） | Hold WNS（ns） |
|---|---:|---:|
| Cpu | +0.280052 | +0.0528152 |
| Tpu | +0.382773 | -0.120269 |
| Bus | +3.61395 | +0.0684113 |

集成全局 setup 余量仅 0.449181 ps，不能据此声称有工程余量。
全局最差 setup 比上述寄存器数据端点统计更差，需查看原始路径，不能直接认定 CPU 为最差端点。
用户随后回传 internal_hold.rpt 起止点摘要，确认最差路径为
`Tpu/Core/Sram/RequestWriteData_reg[...]` 到
`Tpu/Core/Sram/Storage[0].Banks[0].Memory/Macro`，集中在 SRAM 写数据入口。
两顶层 hold 均 FAIL，未达时序收敛；工具执行成功不等于时序通过。
用户明确 CPU setup 暂不处理，当前只修 SRAM hold。

已准备 v5 单文件恢复脚本 `tpusoc_sram_hold_20261102_v5.sh`，19,656 字节，
SHA256 `fa174c9ad2504d840cae51f442c0e04e83d373aa5b06fb3575bb792964ee7cba`。
复用本次已映射 DDC/库、冻结 SRAM 层级外单元，做一次 600 秒限时 hold-only compile；
保持时序约束，保存候选后重新检查完整 setup/hold，不覆盖原 DDC。
本地 Tcl 策略检查、六项复用输入保护测试、内嵌文件哈希和 Bash 语法通过；
服务器 v5 已执行：优化进度在约 28 秒显示 min-delay cost 为 0，
整个 DC 调用约 401 秒。候选 DDC/网表/SDC 已写出，随后
`HOLD_REPAIR_ERROR: Outside-SRAM leaf count changed` 触发，流程 FAIL。
尚未输出最终 WNS，不能把 min-delay cost=0 当作已通过验收。
原因可能涉及真实单元或工具常量伪单元，截图不足以判定。

恢复目录按截图为原运行下 `sram_hold_20261102_QUhgew`。
新增 v5b 只读补报脚本 `tpusoc_sram_hold_report_20261102_v5b.sh`，23,347 字节，
SHA256 `7a010d67cb9d12b3f93a738437efe12eb83757fe8c441d6e4ebff84e348ba808`。
分别读取原始及候选 DDC，生成实际前后 WNS、SDC 比较、层级外逐单元增删/引用变更表，
不会重新 compile，不改候选或原始 DDC。差异不会阻断 WNS 报告；
时序 PASS 与层级外变更待审分开呈现，常量伪单元差异也不直接视为等价证明。
本地七项报表/差异/哈希保护测试、Tcl 完整性、只读命令检查及内嵌哈希通过。
用户已回传服务器 v5b 完整补报结果，报告目录为恢复目录下
`report_recovery_20261102_buKfXG`（按截图转录）。

| 集成顶层候选 | 修复前 | 修复后 |
|---|---:|---:|
| Setup WNS（ns） | +0.000449181 | +0.000449181 |
| Hold WNS（ns） | -0.120269 | +0.00112969 |
| SRAM 输入 Hold WNS（ns） | -0.120269 | +0.00112969 |
| 库叶单元面积总和 | 726669.104784 | 728222.970384 |

面积增加 1553.8656 个原始库面积单位，约 0.214%。原时序要求完全一致，
原始/候选 DDC 和库输入哈希均保持不变。
`TIMING_REPAIR_STATUS: PASS (TT pre-layout)`；该集成候选在当前 TT 综合约束下
已消除 hold 违例。setup 保持原值，按用户要求不在本轮优化。
修复后最差 hold 起点变为 `Tpu/Core/Sram/RequestWriteMask_reg[0]`，
终点仍为 SRAM Macro，报告 slack 为 +0.001130 ns（显示舍入）。

层级外变化：真实单元 18 项、常量伪单元 0 项，Cpu/ 下真实单元变化 0 项。
用户随后回传完整 outside_changes.tsv，18 项均为 ADDED：

| 新增单元 | 库引用 | 数量 |
|---|---|---:|
| Tpu/Core/U739 至 U750 | BUFV32RQ_12TR40 | 12 |
| Tpu/Core/U751 至 U754 | BUFV32_12TR40 | 4 |
| Tpu/Core/U755 至 U756 | BUFV24RQ_12TR40 | 2 |

变更类型核对完成：SRAM 父层级 Tpu/Core 下只新增 18 个 buffer，
没有删除或替换原有的层级外单元。原校验只允许 Tpu/Core/Sram/*，
父层级新增实例超出了该路径前缀，因此触发数量校验。
不再把这项数量校验失败当作时序修复失败。
原服务器报告的 `CANDIDATE_REVIEW: PENDING_OUTSIDE_CHANGE_REVIEW` 保留作原始证据；
此记录补充人工清单核对结果，不改写服务器报告。
CPU 计数仅证明叶单元名称/库引用未变，不证明完整连线等价。
网表形式等价和 buffer 连线等价尚未验证，不将清单核对当作这些验证的替代。

当前可复用的集成候选是恢复目录 `E203TpuBackend/` 内同名的
`E203TpuBackend_hold_candidate.ddc`、`.v`、`.sdc` 三件套。
本次修复发生于映射网表，上游 RTL 保持未修改；初始 mapped DDC 仍保留原 hold 违例。
重新从 RTL 综合时须重现 hold 修复步骤，不能把初始网表当作本次通过的候选。
本轮状态记录为：集成候选在原 150MHz TT 工程预算下 setup/hold PASS，
层级外新增单元类型核对完成，物理签核/形式等价未执行。

PR 整理补充：打包器允许 Server 工具独立提交，始终从固定硬件提交导出源码，
拒绝不匹配的硬件修改。新增包名使用独立 --tag，历史 v4 清单及恢复脚本的
严格绑定保持不变。16 项 Python 测试、三个 Tcl 策略测试、Shell 语法和
新打包清单验证通过；此项工具整理不重新宣称一次服务器时序运行。
详见 [恢复说明](../SingleClock/HoldRecovery.md)。
当前范围仍不含布局/CTS、提取寄生、多角签核、外部 TCM 实体宏或 DDR PHY。
