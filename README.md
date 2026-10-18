# KWT-1 关键词唤醒 Transformer 加速器

面向 2026「中国电子杯」高校 ICT 大赛研究生赛题三（飞腾命题）的 RTL 实现。

- 模型：KWT-1（`d_model=64`, `mlp_dim=256`, 12 层 PostNorm Encoder, 99 token）
- 量化：权重 int4（per-output-channel），激活 int8
- 目标：150 MHz，面积 ≤ 2.25 mm²，Top-1 下降 ≤ 2 pp
- **实测：定点精度 96.17 %（浮点 97.33 %，下降 1.17 pp）**
- **实测：单帧推理 1,477,755 周期 = 9.85 ms @150 MHz**（含参数装载，较初版 35.5 ms 优化 -72.3 %）

## 目录结构

```
rtl/            18 个可综合模块（已验证 bit-exact）
  kwt_dot64.v           64 点积（int8 × int4 → int32）
  kwt_gemm4.v           4 通道并行 MAC（256 MAC/cycle）
  kwt_gemm_engine.v     通用 GEMM 引擎（参数化 IN/OUT/TOKENS/WB）
  kwt_requant.v         int32 → int8，Q1.31 乘数、四舍五入、饱和
  kwt_exp_lut.v         softmax 指数表（256 项）
  kwt_softmax.v         单行 softmax（N=99）
  kwt_rsqrt_lut.v       LayerNorm 倒数平方根表
  kwt_layernorm.v       64 宽行 LayerNorm（LUT + 3 次牛顿迭代）
  kwt_gelu_lut.v        GELU 查表
  kwt_gelu.v            GELU 变换
  kwt_align_add.v       残差对齐（Q10 双乘数）
  kwt_attn_qkv.v        Q/K/V 三引擎
  kwt_attn_score.v      QKᵀ
  kwt_attn_av.v         P·V
  kwt_attention.v       完整注意力块
  kwt_encoder_layer.v   单层 PostNorm Encoder
  kwt_encoder_12.v      12 层调度 + 参数 ROM 切换
  kwt_top.v             整机（MFCC → patch_proj → 12 层 → head → argmax）

tb/             14 个 testbench（逐位比对，无容差）
tools/          数值模型、标定、向量生成器
doc/            设计文档 00–07
models/         权重（npz）与量化参数（scales.json）
sim/            仿真工作目录 + run_all.ps1 一键回归
rtl_verified/   当前通过验证的 RTL 快照
tb_verified/    当前通过验证的 TB 快照
```

## 快速验证

```powershell
cd e:\chipdesign\sim
.\run_all.ps1                 # 生成向量 → 编译 → 逐级仿真
.\run_all.ps1 -SkipVectors    # 复用已有向量
.\run_all.ps1 -OnlyTop        # 只跑整机
```

预期输出：

```
=== tb_kwt_attention ===      PASS: attention 1584 words bit-exact        (36445 cycles)
=== tb_kwt_encoder_layer ===  PASS: encoder layer 6336 values bit-exact   (105694 cycles)
=== tb_kwt_encoder_12 ===     PASS: 12-layer encoder 6336 values bit-exact (1463497 cycles)
=== tb_kwt_axi_slave ===      PASS: AXI4-Lite slave, all registers behave
=== tb_kwt_top ===            PASS: full KWT-1 inference, 3/3 samples     (1477755 cycles = 9.85 ms)
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `doc/00_赛题要点.md` | 赛题要求、评分表、计时规则 |
| `doc/01_总体计划.md` | 里程碑、进度、风险 |
| `doc/02_数值方案实验计划.md` | 量化方案对比实验（W8A8 / W4 / W4pc） |
| `doc/03_架构方案.md` | MAC 规模、参数装载分析、存储组织 |
| `doc/04_定点数值规范.md` | 逐位规范：int4 权重、int8 激活、Q1.31 requant、舍入/饱和 |
| `doc/05_定点方案与实测.md` | 最终方案 + 5 个数值 bug 复盘 |
| `doc/06_注意力微架构.md` | 3 个 GEMM 引擎、buffer 映射、周期估算 |
| **`doc/07_整机验证结果.md`** | **完整验证矩阵、周期分析、ROM 布局、复现命令** |
| `doc/08_AXI寄存器映射.md` | AXI4-Lite 从机寄存器表、软件流程、与 `kwt_top` 的连接 |
| `doc/09_综合与时序.md` | 综合脚本用法、面积估算要点、Artix-7 实测 |

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
- **任务前清空数据与参数缓存** → 参数装载不可省略（当前占 15.3 %）
- RTL 输出须与提交的数值模型**逐位一致**（本工程全部采用 `!==` 严格比对）

## 待完成

| 项 | 阻塞原因 |
|---|---|
| 任务 3：SoC 集成 + E203 驱动 | 等组委会下发 SoC 平台工程（AXI 互连、存储映射） |
| 任务 7：综合、时序、面积、功耗 | 等组委会下发标准单元库与 SRAM macro |

这两项的接口已在 `kwt_top.v` 中按 AXI-4 从机 + 参数 ROM 的形式预留。
