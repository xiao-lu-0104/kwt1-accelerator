# 编码器 MMIO 接口（2026-10-30 v11）

`rtl/kwt_encoder_axi_top.v` 将 v10 参数握手编码器接到竞赛平台的无 ID AXI 扩展口。
`rtl/kwt_encoder_mmio.v` 负责总线、参数拼接、任务控制及输出 SRAM。
原 `kwt_axi_top.v` 仍对应 MFCC/分类演示接口。新的入口处理十二层 encoder 任务。

## 验证范围

- v10 服务器真实宏七组回归已通过，详情见 [参数接口接入](SoC参数接口接入.md)。
- v11 本地 XSIM 协议测试通过：AW/W 先后顺序、B/R 背压、参数阻塞期间读状态、
  错误响应、拒绝 burst、两次任务、半条参数复位、输出打包和计数快照。
  本地存储模型是显式测试替身 `tb/models/kwt_ramtp_contract.v`。
- C 驱动经主机 GCC `-std=c11 -Wall -Wextra -Werror` 编译和控制流模型测试通过。
  覆盖两次 6336 字节任务、90768 参数字、逐层回调、等待、超时及失败复位。
- `tb_kwt_encoder_axi` 使用总线功能主机和真实编码器，完整读回并逐位比较 golden。
  服务器三组回归现已通过；这一测试没有实例化 E203 CPU。
- E203 执行驱动、CPU 完整任务周期、集成顶层 PPA 均待验证。

## v11 服务器实测

隔离工作目录：`~/soc/kwt_sram_20261030_202253_*/`。
SRAM 相位短测、MMIO 协议和完整 AXI 编码器三组测试全部通过。
完整任务从 AXI 写入 1584 个输入字、90768 个参数字，读出 1584 个输出字，
共 6336 字节逐位匹配 golden。核心计数 3476758，外设诊断计数 3502109。
本地 XSIM 加显式 SRAM 测试替身得到相同结果；服务器使用原始真实宏模型。
这是总线功能主机结果，尚无 CPU 端到端周期，也没有本轮综合/时序闭合结论。

## 总线和任务约定

基址 `0x40000000`，窗口 64 KiB。地址/数据均为 32 位、字节序为 little endian。
有效操作要求 4 字节对齐、SIZE=2、LEN=0、LOCK=0、BURST=FIXED 或 INCR。
读写地址与数据可独立到达，允许背压；最多各一个未完成的读和写请求。
平台桥的正常请求均为单拍。

不支持的 burst 按 LEN 消耗写拍或返回错误读拍，最后一拍正确给出 RLAST，
不执行输入/参数/控制副作用。窗口外返回 DECERR，其他非法访问返回 SLVERR。
正常 burst 请求必须提供符合 LEN 的拍数；接口不对违反协议后停止发拍的主机补拍。
AXI 错误由平台异常机制处理；状态 ERROR 记录的是核心输出/完成协议错误。

输入和输出必须顺序传输完整 32 位字，每个任务均为 1584 字、6336 字节。
输入仅在启动前写入；输出仅在成功完成后读取一次，地址从窗口起点递增。
计数在实际读/写握手时推进。输入写响应在四个字节全部送入核心后返回。
输入/参数非零部分字节写入返回错误；零 WSTRB 为无副作用空写。

每个任务先 soft reset，写完整输入，START，再按 12 层顺序写完整参数流，
等待 DONE，顺序读完整输出。下一任务先 soft reset。只允许单个软件所有者操作。
复位清除有效计数、核心状态和完整/半条参数，不清空 SRAM 数据阵列；
旧输出通过状态和计数失效。存在未完成的 AXI 读时，soft reset 返回错误，保留该响应。

## 寄存器

以下偏移均相对于基址；除 CTRL、PARAM_DATA 和输入窗口外均只读。

| 偏移 | 名称 | 内容 |
|---|---|---|
| 0x0000 | CTRL | 写 bit0=START，bit1=soft reset；同时写 3 非法，0 空操作；由 WSTRB[0] 控制 |
| 0x0004 | STATUS | bit0 busy，1 done，2 error，3 参数可写，4 输入完整，5 参数字已全提交，6 成功完成，7 任务计时中 |
| 0x0008 | CORE_CYCLES | 首次 DONE 时锁存编码器 cycle_count，包含参数等待 |
| 0x000c | TASK_CYCLES | 外设诊断周期，窗口定义见下文 |
| 0x0010 | INPUT_WORDS | 已写输入字，完成为 1584 |
| 0x0014 | PARAM_WORDS | 已接收参数字，完成为 90768 |
| 0x0018 | OUTPUT_BYTES | 核心已产生输出字节，完成为 6336 |
| 0x001c | READ_WORDS | 已读输出字，完成为 1584 |
| 0x0020 | REQUEST | bits[23:20] cur_layer，[19:16] ld_sel，[13:0] ld_addr；调试用途 |
| 0x0024 | SIGNATURE | 固定 0x4b575431 |
| 0x0030 | PARAM_DATA | 顺序写参数字；两个 32 位字拼成低字在前的 64 位记录 |
| 0x1000–0x28bf | INPUT | 6336 字节输入，顺序整字写入 |
| 0x4000–0x58bf | OUTPUT | 6336 字节输出，顺序整字读取 |

参数拼接缓冲遇到核心停顿时对 AXI 写施加背压。驱动先轮询 STATUS[3] 再写，
避免 CPU 长时间阻塞在参数写事务中。STATUS[5] 表示总线已提交所有字，
最终成功还要求核心实际消费完参数且输出字节数正确。
参数文件格式及逐层记录数见 [参数接口接入](SoC参数接口接入.md)。

## C 驱动与周期口径

`sw/kwt_encoder.h`、`sw/kwt_encoder.c` 提供 `kwt_encoder_run`。
调用者提供输入/输出各 6336 字节、一个 7564 个 uint32_t 的 scratch（30256 字节），
以及按层填充 scratch 的回调；驱动不分配整模型存储。
每层 7564 字、12 层 90768 字。回调应从平台的模型存储源读取正确层数据。
主机模型测试不能替代该实际存储路径的验证。

RISC-V M-mode 通过 `mcycleh/mcycle/mcycleh` 稳定读取 64 位计数，MMIO 前后执行 fence。
`metrics.cpu_cycles` 从复位后首次输入准备之前开始，到最后输出存入调用者缓冲后结束，
包含参数回调、CPU 指令、总线等待和结果拷贝。只有实际 RISC-V 执行才设置 valid；
当前尚无 CPU 实测数值。若平台禁用 mcycle 或修改时钟域，需要在平台接入时处理。

外设 TASK_CYCLES 从第一个输入 AW 握手后开始，到最后一个输出 R 握手结束；
它不包含 CPU 将最后的 RDATA 存入共享内存的延迟。CORE_CYCLES 只覆盖核心运行。
二者都是诊断计数，不能直接作为 CPU 完整任务时间。
32 位诊断计数按模 2^32 回绕。软件轮询上限是每次等待的最大状态读取次数。

## 存储与时序

新增 4096×16 bit 输出缓冲（8 KiB），默认宏绑定预计新增 4 个 RAMTP1024X16。
完整外设预计为 44 个物理宏、88 KiB。现有 40 宏核心的历史面积、时序报告
不能作为这个新顶层的报告；需后续重新综合并核对实际宏数量。

宏读写仍采用 root 上升沿读、锁存后 root 下降沿写，保留碰撞检测及库时序弧。
150 MHz 相位短测开启 specify；完整无 SDF 的 AXI 数值测试使用 +notimingcheck。
原 1 ns hold 基线未闭合，100 ps 试验通过仍只属于工程试验。

## 服务器复现

包 `kwt_encoder_mmio_20261030.tar.gz` 包含源码、向量、驱动、测试平台和校验清单。
不含第三方模型/库/旧网表。解压到新目录：

```bash
mkdir -p ~/soc/kwt_encoder_mmio_20261030
tar -xzf ~/Desktop/kwt_encoder_mmio_20261030.tar.gz -C ~/soc/kwt_encoder_mmio_20261030
bash ~/soc/kwt_encoder_mmio_20261030/tools/run_kwt_sram_binding.sh --encoder-mmio
```

共三组：SRAM 相位短测、MMIO 协议测试、AXI 完整十二层编码器。
`--suite unit` 只跑前两组。新运行输出 v11 修订号和独立 WORK_DIR。
成功须有三组 PASS、`AXI_MMIO inputs=1584 parameter_words=90768 output_words=1584 ...`，
及 `FUNCTIONAL_RESULT: PASS`。脚本检查缺失标记、错误诊断和不完整传输。
本模式不执行综合，不允许叠加 `--synth`（原综合脚本仍以独立核心为顶层）。

本地 C 测试可运行：

```bash
gcc -std=c11 -Wall -Wextra -Werror -O2 -I sw tb/test_kwt_driver.c -o kwt_driver_test
./kwt_driver_test
```

重建服务器包：`python tools/make_encoder_mmio_package.py`。
下一步在 E203 隔离副本替换示例 AXI 外设、交叉编译驱动并验证 CPU 发起的完整任务。
