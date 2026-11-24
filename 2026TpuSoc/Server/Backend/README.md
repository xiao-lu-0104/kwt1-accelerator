# 当前后端工作入口

主线为 **SMIC 40nm 服务器 ASIC 综合与时序**，用户于 2026-11-02 明确指定。
源码为上游 `a1d0c9a`，没有修改跟踪的 RTL。旧 `Server/Run.sh` 仅支持旧基线，勿混用。

**当前恢复入口：`RecoverAsic.sh --run-dir 原v3b工作目录`。**
服务器真实宏 568 个读回值与 CDC 1024 包已经通过，TT DB 已转换。
DC 对适配层未使用的 real TCO 参数报 VER-177；本地已删除该参数。
恢复脚本校验原源码/测试/缓存库，在新目录只重跑两个顶层综合。仍没有实际 PPA/时序结果。
首次执行流程入口仍为 `RunAsic.sh`，后续从本地源生成的 v3c 包包含此修复。
运行与约束边界见 [ASIC 说明](Asic.md)。

当前先执行 `ReadMacro.sh`，收集服务器 `RAMSP1024X16` 真实逻辑端口和 TT 手册。
它依赖包内只读解析工具，不改共享库，不进行综合。v1 对两个同名原始定义会报错；
v2 已支持逐一保存定义和条件编译指令，仍不擅自选择生效分支。
真实端口及静态控制脚已审查；厂商模型验证、ASIC 综合均待后续实际执行。

上游的 `kwt_sp_memory_model` 是行为模型；v3 在 ASIC 源码列表中以实际宏适配层替换其实现，
保留原 `TpuSram` 请求、时钟与流水。网表需验证恰有 56 个真实厂商宏。

`RunFpga.tcl` / `Run.sh` 是独立的 FPGA 参考复现入口，支持 `soc100`、`soc150`、`tpu150`。
它使用 Artix-7 BRAM 推断，不提供 SMIC 40nm 的面积、延迟或签核结论。
源码、约束及各域 setup/hold、CDC max-delay、bus-skew 报告按 run 保存。

`LocalReset.vlt` 仅供本地 Verilator 5.050 的复位同步器告警适配，保留原功能断言。
`MakePackage.py` 固定 `a1d0c9a`，默认生成 ASIC v3，拒绝覆盖现有包，避免改变已上传包的含义。

结果与证据边界见 [本轮记录](../Results/20261102_Backend.md)。
