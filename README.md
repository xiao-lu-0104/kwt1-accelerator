# KWT-1 关键词唤醒 Transformer 加速器

面向 2026 嵌入式芯片与系统设计竞赛 · 芯片设计赛道（研究生组）的 RTL 实现。

**2026-10-30 更新：CPU 基线 67/67、真实 SRAM 宏十二层逐位回归均通过。原约束真实宏综合总单元面积 0.9654 mm²；TT setup +0.049 ns，hold −1.04846 ns。43 秒诊断已完成；100 ps hold 裕量试验的面积为 0.9788 mm²、setup +0.049 ns、hold −0.100 ns，仍未闭合，不能替代原约束结论。**

| 门槛项 | 赛题要求 | 实测 | 状态 |
|---|---|---|---|
| 功能精度 | Top-1 下降 ≤ 2 pp | 96.67 %（浮点 97.33 %，−0.67 pp） | ✅ |
| RTL 与数值模型一致 | 逐位一致 | 全部 testbench 用 `!==` 严格比对通过 | ✅ |
| 时序 | 150 MHz | 真实宏 TT：setup **+0.049 ns**、hold **−1.04846 ns** | setup 通过，hold 待处理 |
| 面积 | ≤ 2.25 mm² | 真实宏综合 **0.9654 mm²**（含 SRAM） | 单元面积通过 |

综合环境：SMIC 40 nm `SCC40NLL_VHSC40_RVT`，tt 1.1 V / 25 ℃，Design Compiler
T-2022.03-SP5，周期 6.667 ns 另加 1.0 ns 时钟不确定性。脚本见 `syn/dc_compact.tcl`。

### 核心指标

- 模型：KWT-1（`d_model=64`, `mlp_dim=256`, 12 层 PostNorm Encoder, 99 token, 1 个注意力头）
- 参数量：607,308
- 量化：权重 int4（per-output-channel），激活 int8，Q1.31 requant
- 架构：单条共享 **64 MAC** 数据通路，按 token 逐行处理注意力 / FFN / LayerNorm
- 存储：**37 个逻辑 SRAM，80 KiB**；服务器宏绑定方案为 **40 个 RAMTP1024X16**（4096 深度用 4 块拼接）
- 精度：定点 **96.67 %**，浮点 97.33 %，下降 **0.67 pp**
- 性能：`tb_kwt_top` 整机 **3,247,169 cycle = 21.648 ms @150 MHz**；
  `tb_kwt_encoder_12` 编码器本体 **3,232,909 cycle = 21.553 ms**

### 资源用量

| 资源 | ASIC（SMIC 40 nm） | FPGA（XC7A100T-2） |
|---|---|---|
| MAC（int8×int8 → int16） | **64** | 64（DSP + LUT 实现） |
| 触发器 | **26,196** | 18,083 FF |
| 标准单元逻辑 | 约 0.255058 mm²（组合与时序单元之和） | 17,069 LUT（另计 FF） |
| SRAM | 库 cell 面积 0.710314 mm² / 80 KiB / 40 个物理宏 | 2 × RAMB36 + 43 × RAMB18 |
| 加速器总单元面积 | **0.9654 mm²**，包含真实 SRAM 宏 | — |

> ASIC 与 FPGA 触发器数不同不是矛盾：FPGA 版把 `kwt_packed_sram` 的 bank 控制寄存器
> 连同存储体一起塞进了 BRAM，ASIC 版存储体是宏，这些寄存器变成真实触发器。
> 26,196 是早期黑盒综合的时序单元数；当前触发器数量需读取本轮资源报告。

> 最新真实宏综合总单元面积为 965,371.79 µm²，其中 SRAM 为 710,313.75 µm²，
> 标准单元逻辑约 255,058.04 µm²。早期 260,027 µm² 黑盒报告已由本轮结果替代。
> 物理布局布线开销和带活动标注的功耗仍需后续评估。

> 9.85 ms 等历史性能记录属于旧版（Gen2）配置，已被当前紧凑版取代，不再适用。

## 目录结构

```
rtl/            29 个模块（其中 8 个为旧代模块，紧凑路径不再使用）
  # —— 当前紧凑路径（比赛配置 COMPACT=1）——
  kwt_encoder_12.v            12 层调度 + 参数 ROM 切换 + xhold SRAM
  kwt_encoder_layer_compact.v 单层紧凑实现（单条 64 MAC 复用）
  kwt_mac16x4_pipe.v          16 输入 × 4 输出 MAC（64 个 int8 乘法 + 4 级加法树）
  kwt_mem16.v                 宏边界（KWT_ASIC_SRAM）与 kwt_packed_sram 宽字打包
  kwt_layernorm.v             64 宽 LayerNorm（牛顿迭代，4 级流水）
  kwt_mul_pipe.v              乘法流水
  kwt_softmax4.v              四路并行 softmax
  kwt_softmax.v               单路 softmax
  kwt_requant_pipe.v          量化流水 int32 → int8（Q1.31、舍入、饱和）
  kwt_requant.v               量化组合版
  kwt_align_add_pipe.v        残差 Q10 对齐（流水）
  kwt_align_add.v             残差 Q10 对齐（组合）
  kwt_gelu.v                   GELU 变换
  kwt_exp_lut.v / kwt_rsqrt_lut.v / kwt_gelu_lut.v   查找表
  kwt_sram_2p.v               精确深度真双口 SRAM 包装
  kwt_top.v                   整机（MFCC → patch_proj → 12 层 → head → argmax）
  kwt_axi_slave.v             AXI4-Lite 从机（寄存器映射见技术文档 §6）
  kwt_axi_top.v               AXI 集成壳（⚠️ 例化的是旧核 kwt_top，非紧凑核）
  # —— 旧代模块（Gen1/Gen2）——
  kwt_dot64.v / kwt_gemm4.v / kwt_gemm_engine.v
  kwt_attention.v / kwt_attn_qkv.v / kwt_attn_score.v / kwt_attn_av.v
  kwt_encoder_layer.v

tb/             31 个 testbench（逐位比对，无容差）
tools/          数值模型、标定、向量生成器
doc/            KWT1加速器技术文档.md（主文档）、ICB总线协议.md、13_EDA平台环境记录.md
                archive/ 下 16 份历史文档
models/         权重（npz）与量化参数（scales.json）
sim/            仿真工作目录 + run_all.ps1 一键回归
syn/            dc_compact.tcl（SMIC 40nm DC 脚本）、run_compact.tcl（Vivado）、kwt_top.xdc
rtl_verified/   当前通过验证的 RTL 快照
tb_verified/    当前通过验证的 TB 快照
```

## 环境准备

仓库只包含源码与必要的权重文件，以下内容因体积原因被 `.gitignore` 排除，需自行准备：

| 内容 | 获取方式 |
|---|---|
| `.venv/` Python 环境 | `python -m venv .venv` 后 `pip install tensorflow==2.15.1 numpy==1.26.4 scipy` |
| `data/speech_commands_v0.02/`（7.8 GB） | 从 Google Speech Commands 官方地址下载后解压到该目录 |
| `external/keyword-transformer/`（314 MB） | `git clone https://github.com/ARM-software/keyword-transformer`，checkout `237e409` |
| `models/ref/`（393 MB 参考张量） | `.venv\Scripts\python tools\export_reference.py --split validation --count 400 --offset 200` |

只有重新生成向量时才需要 `models/ref/`；复跑已有向量的仿真只需 `.venv`（或直接用 `sim/vectors/`）。

## 快速验证

```powershell
cd e:\chipdesign\sim
.\run_all.ps1                 # 生成向量 → 编译 → 逐级仿真
.\run_all.ps1 -SkipVectors    # 复用已有向量
.\run_all.ps1 -OnlyTop        # 只跑整机
```

预期输出（每个模块以 `PASS` 开头）：

```
=== tb_kwt_encoder_layer_compact ===  PASS: 6336/6336 values bit-exact (253143 cycles, 4-lane softmax)
=== tb_kwt_encoder_12 ===             PASS: 12-layer encoder 6336 values bit-exact (3232909 cycles = 21.553 ms)
=== tb_kwt_top ===                    PASS: full KWT-1 inference, 3/3 samples (3247169 cycles = 21.648 ms)
=== tb_kwt_axi_slave ===              PASS: AXI4-Lite slave, all registers behave
```

逐位一致性另经 VCS 交叉验证：与 xsim 结果完全一致（`tb_kwt_encoder_12` 1,591,853 cycle 配置下，3/3 样本通过，CPU 时间 32 s）。

## 文档索引

| 文档 | 内容 |
|---|---|
| **`doc/KWT1加速器技术文档.md`** | **主文档**：项目概述与赛题约束、数值方案、架构与四代演进、验证矩阵、性能资源、AXI 接口、复现指南、待办 |
| **`doc/ICB总线协议.md`** | E203 ICB 总线协议（信号表 / 时序规则 / 从机视角 / SoC 集成落点分析） |
| `doc/13_EDA平台环境记录.md` | FTP / VNC 连接与踩坑记录 |
| `doc/2026芯片设计赛道赛题指南.pdf` | 赛题原文 |
| `doc/2026NICT EDA平台_用户登录及使用手册_V10.pdf` | 服务器使用手册 |
| `doc/archive/` | 16 份历史文档（00–12、14–16），内容已合并进主文档 |

## 数值流水线

```
MFCC 98×40 int8 (s=2.752)
  → patch_proj 40→64 (int4, 补零到 64 通道)
  → + class token + pos_emb （均为 s_x=0.1086 域常数）
  → 12 × Encoder (s_x → s_out=0.0448)
  → head 64→12 (int4, 补零到 16)
  → argmax → 4 bit 类别
```

每层的 stage scale 定义在 `models/quant/scales.json`，由 `tools/calibrate.py` 自动标定。

## 关键约束（来自赛题）

- 研究生 1 个任务 = 1 次十二层编码器计算并写回
- **计时从"输入与参数开始装载"到"结果全部写回"**
- **任务前清空数据与参数缓存** → 参数装载不可省略（紧凑版在每层开始前顺序扫描参数 ROM，
  3,782 拍/层 × 12 层 = 45,384 拍 ≈ 0.30 ms @150 MHz，占总推理时间约 1.4 %）
- RTL 输出须与提交的数值模型**逐位一致**（本工程全部采用 `!==` 严格比对）

## 待完成

| 项 | 状态 |
|---|---|
| 综合 / 时序 / 面积 | 真实宏 0.9654 mm²；TT setup +0.049 ns，hold −1.04846 ns 待处理 |
| 功耗与单任务能耗（12 分） | ⬜ 待做：需 SAIF + `report_power`，另需补 SRAM 宏功耗 |
| SoC 集成（20 分） | ⬜ 待做：平台已下发（`e203_hbirdv2`），总线为 **ICB**，需写 ICB 从机 + C 驱动 |
| 吞吐口径（12 分） | ⬜ 待做：把参数装载与总线等待按赛题计时规则并入 3,232,909 cycle |
| SRAM 宏绑定 | 40 个真实宏的功能、面积及综合时序接入已验证；hold 尚未闭合，见 [SRAM宏绑定操作](doc/SRAM宏绑定操作.md) |

集成前必读 `doc/ICB总线协议.md`，其中记录了三个已知问题：

1. **`kwt_axi_top.v` 例化的是旧核 `kwt_top`**，SoC 集成应改用 `kwt_encoder_12`。
2. **`kwt_encoder_12` 的参数是扫描式 ROM 接口**（`cur_layer` / `ld_sel` / `ld_addr` 输出，`rom_*` 输入），
   607,308 × 4 bit ≈ **304 KB** 权重需在 SoC 层解决存储；扫描严格顺序、16 nibble/拍，
   实测 FSM 约 3,782 拍/层，12 层共 **45,384 拍 ≈ 0.30 ms @150 MHz**（占总时间 1.4 %）。
   ⚠️ 当前 `rom_*` 是**零延迟**接口（`ld_wgt = (state==S_LW)` 直接吃同拍数据），
   接入同步 SRAM / Flash 前必须先加 `rom_valid` 握手，否则集成无法进行。
3. **地址映射与寄存器规范**尚未从设计说明中确认，确认前勿随意假定。
