# SMIC40 单时钟 ASIC 验证工具

当前硬件基线固定为 `88e529eff28f4ba75fc250fe2e03310e267b3af7`，
ASIC 集成顶层为 `Backend/E203TpuBackend.sv`：CPU、NICE、TPU、AXI 共用 150 MHz Clock。
本目录提供真实 SRAM 适配、厂商模型功能测试、TT 综合/STA、映射检查和历史 checkpoint 恢复工具。

## 入口

| 路径 | 用途 |
|---|---|
| `SingleClock/MakePackage.py` | 导出固定硬件基线与当前工具，生成带 SHA256 清单的源码包 |
| `SingleClock/Run.sh` | 在已解包源码包中运行厂商宏测试及两个顶层的 DC 综合/报告 |
| `Backend/SpFoundry.sv` | 用真实 RAMSP1024X16 替换上游显式 bank 分支的通用模型 |
| `SingleClock/LocalTest.sh` | 本地单时钟 E203 单层/十二层功能回归 |
| `SingleClock/HoldRecovery.md` | 2026-11-02 v4 运行的 v5 hold 修复和 v5b 只读补报 |
| `Results/20261102_SingleClock.md` | 实测结果、恢复过程、适用范围 |

没有随源码提交厂商库、厂商仿真模型、综合网表、DDC、波形或运行产物。
服务器必须已有合法可用的 Synopsys VCS/DC 和 SMIC40/SRAM 交付文件。
标准单元库、SRAM 根路径及工具路径可通过运行脚本中的环境变量覆盖。

## 打包和服务器运行

在仓库根目录执行（Python 3）：

```bash
python Server/SingleClock/MakePackage.py --tag tpusoc_88e529e_single_review
```

产物位于 `workspace/Server/`。将 tar.gz 传到服务器，在新目录解包，然后执行
包内的 `Server/SingleClock/Run.sh`。该入口要求包根有 `MANIFEST.sha256`，
不能直接把未打包的 Git 工作树当作运行包。每个顶层综合最多 30 分钟，
默认分别运行 `TpuNiceAxi` 和 `E203TpuBackend`，可用 `--top tpu|soc` 单独选择。

工具可以提交在硬件基线之后；打包器始终从固定硬件提交导出 RTL，
并检查当前硬件、模拟器和 E203 子模块与该基线一致。每个 artifact 名称只能创建一次，
需要另一个快照时使用新的 `--tag`，包内清单记录实际工具文件的哈希。

56 个 `RAMSP1024X16` 对应 112 KiB。适配层用 `TPU_SRAM_MODEL` 选择原有显式
bank 分支，提供同名接口，并实际例化厂商宏。默认逻辑端口 EMA=2、EMAW=0、RET1N=1，
CEN/GWEN/WEN 低有效。综合前后核对宏数量及叶单元映射。

真实宏 RTL 测试保留输出路径延迟，禁用理想 RTL 的 timing checks；其 PASS 仅指功能。
STA 使用实际标准单元和 SRAM Liberty。工程预算为 6.666667 ns 周期、setup/hold
uncertainty 0.2/0.1 ns，所有同步 CPU/TPU 路径正常检查。

## 已记录的服务器结果

2026-11-02，集成候选在相同时序约束下完成 hold 修复及只读补报：

| 指标 | 原始映射 | hold 候选 |
|---|---:|---:|
| Setup WNS（ns） | +0.000449181 | +0.000449181 |
| Hold WNS（ns） | -0.120269 | +0.00112969 |
| 库叶单元面积总和（原始库单位） | 726669.104784 | 728222.970384 |

层级外新增 18 个 buffer 的完整类型清单已人工核对，CPU 叶单元名称/库引用变化 0 项。
通过的结果是服务器恢复目录中的 `E203TpuBackend_hold_candidate.ddc/.v/.sdc`，
这些缓冲未写回 RTL。新建运行包的默认综合会保留 hold 结果独立判定，不能继承该候选的 PASS。

v5/v5b 恢复工具严格绑定已记录 v4 清单及该次运行的库和 checkpoint 哈希；
它们用于复现该次恢复，不接受任意新包作为原输入。
完整单元清单核对不等于网表形式等价验证。当前结论限 TT 综合模型，
布局、CTS、寄生参数、多角签核、外部 TCM 宏及 DDR PHY 均不在本流程验证范围。

## 本地检查

```bash
python -m unittest discover -s Server/SingleClock -p 'Test*.py'
tclsh Server/Backend/TestAsicCommon.tcl
tclsh Server/SingleClock/TestConstraints.tcl
tclsh Server/SingleClock/TestHoldPolicy.tcl
```

Tcl 策略测试使用 mock collection，不执行 EDA 工具。
`LocalTest.sh` 需要 Linux/WSL、Verilator、G++、原固件 `workspace/Sw/Soc.bin`、
原参考向量 `workspace/Sim/out/Soc` 和 `Model/.venv`（按项目 Makefile 准备）。
已完成的新顶层本地十二层回归为 15,839,255 CPU/TPU 周期，
DDR 模型设为 150 MHz、600 MB/s、首拍 12 周期、刷新 39/1170；参考输出检查通过。
本地 SRAM 测试替身及参考输入分类检查分别不代表厂商宏时序或真实语音准确率。
