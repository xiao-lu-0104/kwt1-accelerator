# 单时钟 ASIC 运行包：88e529e

上游提交 `88e529eff28f4ba75fc250fe2e03310e267b3af7` 新增
`Backend/E203TpuBackend.sv`。本包使用这个顶层，CPU、TPU、NICE、AXI
共用一个 150 MHz 上升沿时钟。原 FPGA 顶层 `Rtl/E203Tpu.sv`
仍保留 CDC，本次不使用它。

先在仓库根目录打包固定硬件基线和当前工具（Python 3）：

```bash
python Server/SingleClock/MakePackage.py --tag tpusoc_88e529e_single_review
```

源码包位于 `workspace/Server/`。上传并解包后，在包内运行：

```bash
bash Server/SingleClock/Run.sh
```

入口需要包根的 `MANIFEST.sha256`。工具可以提交到新的 Git commit，
导出的硬件始终固定到 88e529e；打包器会拒绝不匹配的硬件修改。
自定义 `--tag` 可以保留不同的工具快照，已有同名产物不会被覆盖。

默认分别综合 `TpuNiceAxi` 和 `E203TpuBackend`；可用 `--top tpu` 或
`--top soc` 单独选择。每个顶层限时 30 分钟。每次新建隔离工作目录，
核对源码和厂商输入哈希，执行真实 SRAM 模型功能测试，再转换 Liberty、综合、报告。

上游 RTL 保持原样。适配层用 `TPU_SRAM_MODEL` 选择上游已有的显式 bank 分支，
但不加入通用行为模型，而由 `Server/Backend/SpFoundry.sv` 的同名接口
实际例化 56 个 `RAMSP1024X16`（共 112 KiB）。EMA=2、EMAW=0、RET1N=1，
CEN/GWEN/WEN 低有效。该适配层及当前 TpuSram 与前轮服务器验证实现一致，
本次仍会重新执行厂商模型测试并检查综合前后宏数量。

真实宏 RTL 功能测试保留模型输出路径延迟、禁用 timing checks；它不证明时序通过。
STA 使用 SMIC40 标准单元和 SRAM 的真实 TT 库。工程预算固定为周期
6.666667 ns、setup uncertainty 0.2 ns、hold uncertainty 0.1 ns，
输入/输出 max delay 1 ns、输入 min delay 0.1 ns、输出 min delay -0.1 ns。
这些是暂定工程接口预算，需与最终外部 TCM/DDR 控制器接口核对。
集成顶层只豁免外部异步复位入口；同步复位顶层 TpuNiceAxi 的复位仍有输入预算。
无 CDC 例外，无全局 hold 修复。所有 CPU/TPU 同步路径正常检查。

主要结果在每个顶层的 `summary.txt`、`internal_setup.rpt`、`internal_hold.rpt`。
集成顶层额外提供 Cpu/Tpu/Bus 寄存器捕获路径报告。面积按映射叶单元库面积求和，
包含全部 SRAM，不等于完整芯片物理面积。`REPORTS_COMPLETE` 仅表示工具执行完毕；
setup/hold 状态各自判定。若报告失败，已先保存 mapped DDC、网表和 SDC。

本地 `LocalTest.sh` 用新顶层运行 E203 控制单层及十二层功能测试，采用本地 SRAM
测试替身，不替代服务器厂商模型和 STA。分类头检查使用仓库参考输入，不能代表语音准确率。

本流程不包含布局、CTS、寄生参数、多工艺角、TCM 实体宏或 DDR PHY；不构成物理签核。

2026-11-02 服务器反馈：两个顶层映射及报告已完成，hold 均 -0.120269 ns。
最差 hold 位于 SRAM 写数据寄存器到宏输入。按用户要求优先修此处，CPU setup 暂不优化。
单文件 v5 恢复脚本及使用方法见 [SRAM hold 恢复](HoldRecovery.md)。
