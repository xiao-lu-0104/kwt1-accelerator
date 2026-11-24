# 竞赛平台原版 CPU 回归

2026-10-29。本步骤验证竞赛 E203 的现有 CPU 指令测试，尚未接入 KWT，
也不替代加速器功能验证或 SRAM 工艺宏的时序验证。

执行状态：运行包已通过 FTP 上传到服务器 `~/Desktop/e203_cpu_baseline_20261029.tar.gz`。
归档 SHA-256 为 `69d4b3f66f9e647df5eb7aca132fa8518ce566086c5e41e768c24fadbba117dd`。
已收到服务器实际结果：PASSED=65、FAILED=2、SELECTED=67、MISSING_GROUPS=0，
最终 RESULT=FAIL。工作目录为 `~/soc/cpu_baseline_20261029_111229_aGHjJu`（以实际终端路径为准）。
首轮失败随后定位为 DIV/REM 仿真参考表达式的有符号上下文问题，详见下一节。
原始失败运行目录保留，CPU 数据通路未修改；修正参考计算后复跑结果见下文。

## 两项失败的定位：仿真参考模型的有符号传播

失败项为 rv32um-p-div、rv32um-p-rem，均触发
`e203_exu_alu_muldiv.v` 中的 CHECK_GOLD_AND_ACTUAL_SAME。
截图中的同一组输入为 rs1=0xffffffec（-20）、rs2=6：

| 运算 | 原参考值 | 硬件写回 | 正确值 |
|---|---|---|---|
| 有符号商 | 0x55555552 | 0xfffffffd | -3 |
| 有符号余数 | 0x00000000 | 0xfffffffe | -2 |

原黄金表达式把有符号除法/余数嵌在带无符号 div_special_res 的条件表达式中，
无符号上下文传播导致 33 位符号扩展后的 -20 被按 8589934572 计算。
该数除以 6 的商、余数正好等于截图里的错误黄金值。
这两次断言触发不等同于硬件算错；也不能因此直接把 DIV/REM 指令测试标为通过，
需要修正参考计算后，让完整指令测试走到最终 TEST_PASS。
日志虽然 exit=0，但有 Fatal 且没有 TEST_PASS，所以运行器判 FAIL 正确。

本地从原文件提取参考表达式，在 XSIM 中精确复现两个错误值。
改为独立的 signed 33-bit 操作数、除数、商及余数线网后，再接入特殊情况选择，
共 1,012 组随机/符号组合/零除/溢出向量通过。
原先的 unsigned DIVU/REMU 参考、特殊情况选择及全部断言不删除。

## 修正参考模型后的隔离复跑

上传包 `e203_cpu_signedref_20261029.tar.gz` 包含更新的运行器及
`patch_e203_signed_reference.py`。执行：

```bash
mkdir -p ~/soc/cpu_signedref_tools_20261029
tar -xzf ~/Desktop/e203_cpu_signedref_20261029.tar.gz -C ~/soc/cpu_signedref_tools_20261029
bash ~/soc/cpu_signedref_tools_20261029/run_e203_cpu_baseline.sh --platform ~/soc/e203_hbirdv2-master --fix-signed-reference
```

修正默认关闭；该命令显式开启后，只改新建回归副本的 synopsys translate_off
仿真参考段，原平台与第一次 65/67 的运行目录保持不变。CPU 可综合数据通路不变，
不会设置 DISABLE_SV_ASSERTION 或关闭断言；仍运行完整可用指令组。
修改前要求源文件的归一化 SHA-256 与已核对基线一致，不一致就停止。
记录 reference_checker_patch.json、同名 .diff、修改前后源码哈希，
最终摘要包含 REFERENCE_CHECKER_FIX=1，与未修正基线清楚区分。

修正工具及运行器的本地检查已通过。服务器完整复跑结果已取得，见下一节。
修正包已通过 FTP 上传成功，第二次尝试完成（第一次为被动数据连接超时）。
归档 SHA-256：`46e184484a7365ec6123eb4ec35589e941a8b81d477528f143b1f6332b38c66c`。

## 服务器实际复跑结果：67/67 通过

2026-10-29，用户提供完整回归摘要截图：

```text
PASSED=67 FAILED=0 SELECTED=67 MISSING_GROUPS=0
REFERENCE_CHECKER_FIX=1
RESULT: PASS (full suite; competition behavior-memory simulation, not macro timing signoff)
```

运行目录时间标记为 `~/soc/cpu_baseline_20261029_113742_*`，确切后缀及完整路径
以服务器日志为准；results.tsv、runner.log、分项日志及参考补丁记录均保存在该目录。
该结果确认：竞赛版 CPU 的上述五类、共 67 项现有指令测试，在修正仿真参考计算、
保留全部原断言、保持可综合 CPU 数据通路不变的条件下通过。

此 CPU 基线阶段完成。其验证范围是竞赛行为存储配置；不代表真实 SRAM 宏时序、
ASIC 总体时序或 KWT 加速器 SoC 集成已经通过。下一阶段按计划绑定加速器内部 SRAM，
并保留本次 CPU 基线及首轮失败证据用于后续回归对照。

## 服务器运行

将上传包解到单独目录后执行：

```bash
mkdir -p ~/soc/cpu_baseline_tools_20261029
tar -xzf ~/Desktop/e203_cpu_baseline_20261029.tar.gz -C ~/soc/cpu_baseline_tools_20261029
bash ~/soc/cpu_baseline_tools_20261029/run_e203_cpu_baseline.sh --platform ~/soc/e203_hbirdv2-master
```

默认运行完整可用指令组，先执行 `rv32ui-p-add`。基础测试失败就停止；通过后继续
rv32ui-p、rv32um-p、rv32ua-p、rv32uc-p、rv32mi-p 下已有的 `.verilog` 测试镜像。
缺少任一组会显示 `MISSING_GROUP` 并把最终结果标为 INCOMPLETE。
这些是平台已有测试，不额外要求安装 RISC-V 交叉编译器重新生成镜像。

若只想执行最小环境检查，在末尾加 `--suite smoke`；它只运行 add，不能当作全回归。
测试镜像不在默认位置时可传入 `--tests-dir /绝对路径`。

## 隔离和通过判据

- 原工程不执行 make install/clean，不改 CPU RTL。脚本优先复制竞赛已有的
  vsim/install/rtl 和 tb（保留其 vcs 宏）；没有安装副本才复制源目录。
- 新目录为 `~/soc/cpu_baseline_日期时间_随机串`，其中执行原版 run.makefile。
  原版 Makefile 会在复制后的 TB 里插入 vcs 宏，不会修改原始 TB。
- 新目录没有旧 simv/compile.flg，必须成功生成新的可执行 simv。
  强制 Bash 的错误退出和 pipefail，并核对编译日志，避免旧 Makefile 的 touch/tee 掩盖错误。
- 每项必须恰好有一次 Test Result Summary 和 TEST_PASS，并确认测试路径正确；
  TEST_FAIL、仿真 Time Out、运行时 Error/Fatal 或文件打开失败均不能报 PASS。
- 编译最长 600 秒；每项仿真最长 120 秒，超时会终止该项并记录。
- 使用竞赛 Makefile 的 +define+FPGA 和 DUMPWAVE=0。本次是行为存储分支的 CPU 基线；
  时钟门控是否使用工艺通用单元由原平台另一个 FPGA_SOURCE 宏决定，二者不混用。

## 回传结果

终端最后会显示：

```text
================ CPU BASELINE SUMMARY ================
PASSED=... FAILED=... SELECTED=... MISSING_GROUPS=...
RESULTS: .../results.tsv
WORK_DIR: ...
RESULT: PASS / FAIL / INCOMPLETE
```

请回传该段。编译失败则回传 COMPILE_FAIL 后的错误及 BUILD_LOG 路径；
出现 ENV_ERROR 则先处理工具环境或测试镜像路径。

每次运行保留 runner.log、build.log、results.tsv、分项日志、输入源码与测试镜像
SHA-256、实际选择的测试列表及环境信息。独立目录保留首次失败证据，可复查和重跑。

## 本地验证范围

脚本通过 Git Bash 语法检查。用隔离的控制流程桩验证了：成功、被掩盖的编译错误、
TEST_FAIL、未完成、错误镜像路径、运行时 Fatal，以及缺测试组的 INCOMPLETE 判据。
这些检查只验证回归运行器，不是实际 E203 CPU 测试结果。
真正的竞赛平台回归结果须由服务器 VCS 执行后确认。
