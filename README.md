# KWT 后端实现与验证

本仓库汇总我的 ASIC 后端、SoC 集成验证、任务评测和服务器复现工具。
当前前端由队友维护，作为[外部依赖](https://github.com/kkk73/2026TpuSoc)使用；本仓库不复制其完整 RTL，
也不合并其提交历史。原有前端已移入 [历史归档](archive/legacy_kwt_project/)。

代码归属、外部依赖及排除规则见 [OWNERSHIP.md](OWNERSHIP.md)，逐文件来源与摘要见
[CONTRIBUTIONS.json](CONTRIBUTIONS.json)。

## 主要代码

| 目录 | 工作内容 |
|---|---|
| `2026TpuSoc/Server/Backend/` | 指定 SRAM 宏绑定、库检查、ASIC 约束与综合恢复 |
| `2026TpuSoc/Server/SingleClock/` | 单时钟验证、时序报告、增量 hold 修复 |
| `2026TpuSoc/Server/SharedAsic/`、`SystemBackend/` | 共享存储集成、门级任务、初始化、活动和系统功耗 |
| `2026TpuSoc/Server/FinalBackend/` | Formality、ICC2 物理库准备及初始放置 |
| `2026TpuSoc/Server/Frontend707cd7f/` | 旧版 DC、SAIF/功耗、PG、分组 IO、CTS、布线及导出 |
| `2026TpuSoc/Server/Frontend6bb1bea/` | 当前 16 MAC 配置的综合、完整任务活动、功耗与二态上电恢复 |
| `2026TpuSoc/Server/Submission20261113/` | WAV/FF1 评测准备、SysBus32 证据检查、结果汇总和清理工具 |
| `release/newpower_6bb1bea/` | 手动 pluma 传输所需的个人恢复与诊断脚本 |
| `doc/reports/` | 后端 Word 报告、PR 配图和功耗结果证据 |
| `patches/` | 对共享前端文件的本地集成改动，仅以补丁保存 |

`Frontend<提交号>` 是历史工具目录名，表示脚本针对的外部版本；目录内不是队友前端的完整源码。
各阶段结果、限制及服务器命令见 [功耗测量说明](doc/功耗测量_20261113_6bb1bea.md)和
[后端全过程记录](2026TpuSoc/Doc/1110版后端全过程与最终交付报告_20261111.md)。

## 已取得的结果与范围

当前外部版本 `6bb1bea`，16 MAC、150 MHz、56 个私有 SRAM：

| 指标 | 结果 |
|---|---:|
| 已综合加速器边界面积 | 0.846539 mm² |
| 其中私有 SRAM | 0.512317 mm² |
| 加速器 setup / hold WNS | +0.197581 / +0.00112969 ns |
| 完整配置运行 FF1：加速器 / 系统功耗 | 32.622239 / 41.293946 mW |
| FF1 系统单任务能耗 | 59.870452 μJ |
| 完整配置运行 Encoder 单层：加速器 / 系统功耗 | 33.240223 / 41.687711 mW |
| Encoder 单层系统能耗 | 199.994055 μJ |

面积边界不含新 CPU/DMA SystemBus 仲裁器，不能直接称最终新增硬件总面积；完整系统 hold 尚未闭合。
功耗为 TT、预布局、零延迟门级活动估计，使用明确二态上电初值并在首个复位时钟后永久释放，
活动覆盖仍需按原始报告复核。这里的 FF1 是完整硬件运行该任务，不是裁掉选做功能的独立 FFN 配置。

历史 `707cd7f` 版本已完成基础 PR、时钟及信号布线、DEF/GDS 导出并在持久盘重开。
PG/DRC 残留与省略的优化阶段在报告中保留；不将其称为物理签核通过，也不当作新版实现结果。

## 准备独立复现工作区

本仓库的历史脚本保留了原来的相对路径布局。一些打包器需读取外部前端 Git 快照和此前的冻结检查点，
不能在只含个人工具的目录里直接假定前端源码存在。用 Python 3.10 或更高版本创建隔离工作区：

```bash
python tools/prepare_backend_workspace.py --destination workspace/replay --all-revisions
```

该命令从队友仓库只读取得前端，在 `workspace/replay/` 中建立各版本工作树，再覆盖本仓库跟踪的个人工具。
依赖仓库的 push URL 会被禁用；不会向任何仓库推送，也不在个人仓库跟踪前端文件。
如需 CPU 和模型子模块，显式加 `--init-submodules`，并按其许可证及数据准备要求使用。

```bash
cd workspace/replay
python 2026TpuSoc/Server/Frontend6bb1bea/BuildDc.py
```

这是打包入口示例，不是本机执行 Synopsys 工具。真实运行还需要服务器已有 VCS/DC/ICC2、
指定工艺及 SRAM 库、库缓存和相应历史输入。旧阶段恢复脚本必须在核对版本、输入清单与检查点后使用。
不使用 FTP 时，通过对应 PowerShell 剪贴板入口将脚本粘贴到服务器 pluma 后保存执行。

## 本地检查

```bash
python -m compileall -q 2026TpuSoc/Server tools
python 2026TpuSoc/Server/Submission20261113/test_submission.py
```

评测检查需 NumPy；部分编排测试需 Bash/Tcl，某些历史测试需要冻结包或服务器环境。
本地 mock/语法检查不表示重新执行过原生 EDA 流程。
