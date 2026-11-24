# 2026-11-04 初赛收尾执行记录

后续共享 SRAM 接入状态见 [11 月 5 日记录](20261105_Shared.md)；下文未完成项描述 11 月 4 日时点。

当前工作目录为 `E:/chipdesign/2026TpuSoc`。本文分别记录服务器截图证据和本地验证，
不把本地结果写作服务器竞赛平台已通过。

## 平台只读核查

用户运行已上传的 `ReadPlatform_e3939d626722.py`，回传完整终端截图。
脚本哈希为 `e3939d6267222eb2e5f06ccc362b7f50b88548fbd225dd3cb027d76b424dfcb2`。
该脚本只采集指定文件的源文本、哈希和安装副本差异，未执行预处理、编译或仿真。

| 项目 | 服务器截图证据 | 接入结论 |
|---|---|---|
| 原工程 | `~/soc/e203_hbirdv2-master` | 以该竞赛版工程为集成基准 |
| ITCM/DTCM | 源目录及安装副本地址宽度均为 18 | 各 256 KiB；合计 512 KiB，分区使用 |
| 基地址 | `0x80000000` / `0x90000000` | 程序放 ITCM，当前层参数/输入/输出按 DTCM 布局 |
| 配置文本 | `E203_CFG_HAS_ECC`、`E203_CFG_HAS_NICE` | 后续编译保留竞赛配置，不移用当前上游 64 KiB 配置 |
| NICE 访存 | NICE 模块声明和 core 的 `nice_icb_*`、`nice_mem_holdup` 接线存在 | 继续核对经 LSU 的读写通路，不另增外存控制器 |
| DTCM 外部口 | `ext2dtcm_icb_*` 存在；控制器优先级仲裁，LSU 优先 | 加载器采用已有外部访问机制 |
| SoC 顶层 | `ext2itcm/ext2dtcm` 的 cmd_valid、cmd_addr 绑零 | 当前入口未接加载器，容量存在不等于装载流程已实现 |
| 仿真源目录 | `vsim/bin/run.makefile` 使用 `vsim/install/rtl`、`vsim/install/tb` | 集成副本和安装副本必须同步并记录实际编译清单 |
| 所选文件比对 | 安装副本缺失 0；内容差异 1，即 `tb/tb_top.v` | 不能外推为整个工程完全一致 |

10 月 29 日历史记录已指出安装副本 `tb_top.v` 额外有 `vcs` 波形宏；本次同名文件
仍有差异，但终端摘要没有展示 diff，不直接断言本次差异仅为该宏。
P0 的容量/静态接口证据已取得；当前集成配置的编译、CPU 冒烟和真实加载仍待完成。

## P1：独立 FF1 候选

采用 [中文执行计划](../../Doc/初赛收尾计划_20261104.md) 中的 CPU 逐行调度方案。
输入保存在 slot 0，FF1 权重/偏置保存在 slot 6，一行输出保存在 slot 1。
新增 EXEC shape 10：rs1 沿用 metadata，rs2 是完整 32 位行号，必须在 0–98。
新增 DMA spec 9：256 个 signed16 元素（512 B）。每行 STORE 完成后再复用 slot 1。
旧融合 FFN、所有旧指令和当前数值规则保留，不增加私有 SRAM，不改 `TpuDma` 内部基址。

`TpuRunFf1` 装载输入和参数各一次，执行 99 次单行 EXEC、99 次 STORE。
拒绝非法地址对齐、参数小数位以及输出地址回绕；RTL 拒绝非法行号、槽位或偏置配置。
最后一次 STORE 的成功响应由原 DMA 完成机制确认。

### 已完成的本地验证

- `make lint nice`：三个顶层 lint、NICE 原协议检查和新增非法行号/槽位检查通过。
  日志：`workspace/Checks/Ff1LintNice_20261104.log`。
- `make firmware`：新增驱动 RV32IMAC 交叉编译通过，保留 `-Wall -Wextra -Werror`。
  日志：`workspace/Checks/Ff1Firmware_20261104.log`。
- `make ff1`：3 个合成/零值/极值场景及 12 层指定参数，共 15 组，
  每组完整 25344 个值逐位匹配；组间不复位。
  随机 DMA 请求/数据停顿、NICE 响应反压、延迟写响应和输出边界哨兵检查通过。
  每组 DMA 读 45952 B、写 50688 B，恰好 99 次写响应。
  日志：`workspace/Checks/Ff1_20261104.log`。

`make ff1` 使用 NICE 指令测试主机和容量受限的通用存储模型，不包含 E203 执行；
该模型的地址和容量只用于本地功能检查，不替代竞赛平台的真实共享 SRAM 访存。
各层 FF1 输入来自对应浮点编码器的 Norm1 输出，再按本设计格式量化；基准结果由
相同输入及参数的定点线性模型生成，没有用初始编码器输入冒充前馈入口。

### E203 与原编码器回归

- `make official` 通过：12 套参数的注意力/单层编码器逐阶段、仅最终输出检查及
  不复位连续换参全部通过，原计算命令合计仍为每层 1288933 周期。
  日志：`workspace/Checks/Ff1EncoderRegression_20261104.log`。
- `bash Server/SingleClock/RunFf1.sh` 通过：真实 E203 执行新增 C 驱动完成 15 组。
  每组 2 LOAD、99 EXEC、99 STORE，读 45952 B、写 50688 B，全部输出逐字节匹配。
  本地 shared-150-MHz 配置中每组程序结束为 264066 周期，仅作为该 AXI 模型下的回归记录；
  输入及参数预装，不换算成正式平台任务吞吐。
  日志：`workspace/Checks/Ff1Soc_20261104.log` 及 `workspace/Checks/Ff1Soc20261104/*.log`。
  测试仍采用单时钟顶层、厂商宏引脚适配层的本地替身及原 AXI 存储模型。
- 使用同一个新构建的 E203 仿真程序回归原固件：单层为 1327674 周期，十二层仅最终
  导出为 15839255 周期，均通过；LOAD/EXEC/STORE 数量和 DMA 字节数保持原口径。
  日志：`workspace/Checks/Ff1Soc20261104/EncoderOne.log`、`EncoderFinal.log`。
  比对在独立的 `EncoderRegression` 向量副本中运行，没有覆盖历史 SoC 实际输出文件。

### 未完成项

- P2 NICE/ICB 访问桥、竞赛平台集成和按周期分层加载尚未实现。
- 新配置的服务器厂商宏完整回归、综合/网表功能、时序、面积和功耗尚未重跑。
  原 `hold_candidate` 只属于旧 checkpoint，不代表本次新增 RTL 已通过 STA。

P1 的本地 RTL/驱动功能已闭环；厂商宏配置和正式平台仍需后续验证。
不标记初赛交付整体完成，不引用核级测试周期作为正式平台任务吞吐。
