# 共享 SRAM 加载与 NICE 访存回归

2026-11-05。数据链路为加载器 → 外部 DTCM ICB 口 → 平台 DTCM，
TPU DMA → NICE memory ICB → 原 LSU → 同一 DTCM 控制器。
控制指令继续使用 NICE LOAD/EXEC/STORE/STATUS，原 CPU/LSU 数据通路保持不变。

## 本次实现

- `Rtl/TpuIcb.sv`：每个 128-bit beat 拆成四个小端 32-bit ICB 请求，一个 outstanding；
  等待每个响应，最后一笔写响应完成后才向 DMA 返回完成。
  错误和越界仍排空声明长度的 payload，最终报告错误；不向总线发出越界请求。
- `Backend/e203_subsys_nice_core.sv`：替代平台示例 NICE 模块，连接 TpuNice 和 ICB 访问桥。
  `nice_mem_holdup=0`，CPU 调度与 DMA 争用按原 LSU 仲裁产生真实等待。
- `Sw/SharedLayout.json`：输入/输出/当前层参数/栈的布局源，生成 C、SV 常量和链接脚本。
  ITCM 放程序；DTCM 按层复用一个 128 KiB 参数缓冲，不常驻完整模型。
- `Sw/SharedMain.c`：等待 ready 序号，运行 FF1 或编码器，发布 released 序号；
  逐层更新尺度，层间激活保留 TPU 内部，最终 DMA 写回后再发布 done。
- `Sim/SharedTest.sv`：真实 E203 CPU、LSU、ITCM/DTCM 控制器及其 SRAM 行为模型。
  加载器只能经 external-to-DTCM ICB 写入输入/权重并读取输出，所有读写均有握手。

原平台的 `tb_top.v` 安装副本只多一行小写 `vcs` 宏，用户已于 11 月 5 日回传 diff。
本回归使用独立 SharedTest，不修改两份原 tb_top，不使用其 CPU 指令测试完成判据。
当前顶层覆盖 CPU/TCM 接入；原平台完整外设/PLL/常开域的 SoC 顶层联调另行完成。

## 计时与检查

文件读取、数值转换、程序初始化、CPU 启动及输出哨兵预置在计时外。
输入/参数未预装到 DTCM：从第一笔输入写请求呈现开始，到最终输出字的 NICE/ICB
成功写响应结束，包含后续逐层装载、就绪/释放通信、CPU 轮询、仲裁和计算。
输出读取比较在计时外；整个计时内不做文件 I/O 或共享存储的直接 memcpy。

检查全部输出、边界哨兵、每层释放、DMA 的字节量、NICE 指令数和最后写响应。
开始前清空 DTCM 和任务有效状态，私有 SRAM 的输入与参数均由本任务重新装载。
测试平台保存的全模型文件数组不属于被测 SoC 存储。

## 本地与服务器入口

本地执行 `bash Server/Shared/Local.sh`。它复制上游源码，仅在隔离副本把 ITCM/DTCM
地址宽度从 16 改为 18，用于本地接口验证；不能标记为竞赛服务器结果。
原 CPU、子模块工作树和原服务器平台均不修改。构建路径和配置差异写入 Scope.json。
首次三项回归通过后，执行 `bash Server/Shared/MoreCases.sh <本地运行目录>` 补齐其余
FF1 场景。当前十七项均已通过，结果见 [11 月 5 日记录](../Server/Results/20261105_Shared.md)。
编译与打包前后由 `Snapshot.py` 核对实际源码、固件及编译输入的哈希。

服务器包在成功的本地回归后由 `Server/Shared/MakePackage.py --run <运行目录>` 生成。
包包含当前工作区 RTL、固件源码和预编译镜像、离线向量、清单及运行器；
不使用旧 `88e529e` 固定导出包。原平台源码及私有库从服务器已有目录读取。

解包后运行：

```bash
bash Server/Shared/Run.sh ~/soc/e203_hbirdv2-master
```

运行器校验提交包和真实 SRAM 模型哈希，优先复制平台实际使用的 `vsim/install/rtl`，
严格要求 ITCM/DTCM 各 256 KiB，不修改其配置或 CPU 断言。
替换示例 NICE 模块，采用真实 56 个 RAMSP1024X16 的功能模型；保留模型输出延迟，
关闭 RTL 仿真中的宏 timing checks。此项不代表 STA 或网表时序通过。

全部十七项任务通过时才打印 `RESULT: PASS SHARED_FUNCTIONAL`。
任一编译、超时、CPU trap、错误数据或计数不符均为失败，保留独立目录和完整日志。
用户已回传正式服务器十七项全部通过；FF1、单层、十二层分别为
332348、1485712、17501035 周期，详见上述执行记录。
新的综合、网表一致性、时序/面积与功耗须在最终平台配置上重新执行。
