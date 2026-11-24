# 紧凑配置的独立 FF1

独立任务计算 `99×64 @ 64×256 + bias`，输出全部 `99×256` signed16 结果。
复用当前 `TpuMatmul`，保留乘加、舍入、偏置及饱和规则，不执行 GELU/FF2。
私有存储继续使用默认 112 KiB 配置，未开启 `TPU_LEGACY_STORAGE`。

## 指令与布局

| 内容 | 定义 |
|---|---|
| 输入 | slot 0，6336 个元素 |
| 参数 | slot 6，转置打包的 16384 个权重后接 256 个偏置 |
| 当前行输出 | slot 1，256 个元素，存储起始偏移为零 |
| 单行计算 | funct7=EXEC，shape=10；src=0、aux=6、param=0、dst=1、bias=1 |
| 行号 | rs2 的完整 32 位值，范围 0–98；源元素偏移为 row×64 |
| 数值尺度 | 第一参数 fraction 为 1–15；rs1 其余字段沿用原 metadata 定义 |
| 行搬运 | DMA spec=9，256 个元素即 512 B；STORE 从 slot 1 搬运 |

NICE 接收后保留完整行号，RTL 在缩窄源偏移前检查范围。非法行号、固定槽位配置或
fraction 产生 command error。原 EXEC 与 LOAD/STORE 的编码行为保留。

驱动入口位于 `Sw/Encoder.h`：

```c
int TpuRunFf1(uint32_t input_addr, uint32_t ff1_param_addr,
              uint32_t output_addr, uint32_t fraction);
```

驱动先装载输入和参数各一次，然后执行 99 次单行 EXEC/STORE。
第 r 行写到 `output_addr + r×512`。只有本行最终写响应成功后才启动下一行，
函数成功返回表示全部 50688 B 已写回。调用方在新任务前准备好对应层的数据和 fraction。
外部地址要求 16 B 对齐，函数拒绝非法 fraction 和输出地址回绕。

## 本地复现

已有官方提取文件 `workspace/Model/official/Input0.npy`、`Layer0.npz` 等时：

```bash
make ff1
make nice
make official
bash Server/SingleClock/RunFf1.sh
```

`make ff1` 生成三种合成/边界场景和十二层各自 FF1 参数与对应前馈入口，
经 NICE 测试主机检查全部输出、写响应、反压和边界，组间不复位。
`make nice` 检查非法行号和槽位及旧协议；`make official` 回归原编码器功能。

`RunFf1.sh` 使用真实 E203、共享时钟顶层和 C 驱动验证同样十五组数据。
需要本地 Verilator、模型 Python 环境与 RISC-V 交叉编译器；沿用
`workspace/HostTools` 中已有编译器包装。该脚本是本地复现入口，并非服务器提交包。

以上 SoC 回归仍用原 AXI 存储行为模型和宏引脚本地替身，输入/参数仿真前已准备好。
它验证 CPU 调度和 FF1 功能，不代表竞赛平台分层加载、冷启动任务吞吐、厂商宏验证或
新综合网表的 PPA 已通过。服务器静态接口证据及本地日志见
[执行记录](../Server/Results/20261104_Preliminary.md)。
