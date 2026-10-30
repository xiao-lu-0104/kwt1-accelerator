# 半拍 SRAM 的保持时间试验（2026-10-30 v9）

半拍版真实宏四组回归和新鲜综合已经完成，最差 hold 路径是
`g_compact.u_enc/q_group_reg[0]` → 参数 SRAM 宏 `AA[2]`，参考时钟为 `CLKA`。
它来自同步读地址，不能与已经通过的宏时钟/写入路径混为一谈。

## 本轮服务器结果：试验通过

用户返回 `summary.txt` 的完整摘要，目录为
`~/soc/kwt_sram_20261030_161124_*/hold_pilot_20261030_165155_*/`。
入口确认输出 `PILOT_HOLD_REPAIR_STATUS: PASS`、`RESULT: PILOT_COMPLETE`。

| 项目 | 结果 |
|---|---:|
| 原 setup WNS | +0.0469837 ns |
| 原 1 ns 裕量 hold WNS | −0.903385 ns，FAIL |
| 试验 hold uncertainty | 0.10 ns |
| 修复后含 SRAM 总单元面积 | 981242.09 µm²（0.9812 mm²），PASS |
| 修复后 setup WNS | +0.047 ns（摘要舍入），PASS |
| 修复后 hold WNS | +0.000272155 ns（+0.272155 ps），PASS |
| 宏时钟 max 路径 slack | +1.00224 ns |
| 写入 max 路径 slack | +1.46429 ns |
| 宏时钟 min 路径 slack | +3.2335 ns |
| 写入 min 路径 slack | +3.11915 ns |

setup 裕量仍为 1 ns，IO 预算保留。相对本轮半拍原基线，总单元面积增加
11075.28 µm²；SRAM 宏数量和容量保持 40 个、80 KiB。
本轮结果说明该网表在 TT 1.1 V / 25℃、100 ps hold 工程假设下经实际修复后
通过了所报告的检查。不能将 +0.272155 ps 舍入为 0 后隐去其很小的剩余余量。
原 1 ns 基线仍是 FAIL，最终时钟预算、其他角及完整交付验证尚未确认。
保留本次 DDC、SDC、网表、SDF、`summary.txt` 及优化前后报告；当前无需重复本试验。

## 修复前路径证据

用户返回的第一条路径包含：

| 项目 | ns |
|---|---:|
| 数据到达 | 0.264810 |
| 宏库 hold | 0.168195 |
| 当前 hold uncertainty | 1.000000 |
| 数据要求 | 1.168195 |
| slack | −0.903385 |

不计 uncertainty 的路径余量为 0.096615 ns。若只在试验中将 hold uncertainty
改为 0.100 ns，同一路径在优化前预计为 −0.003385 ns。这只是固定网表和同一
工艺角下的预算敏感性计算，不能据此宣布路径通过。

## 试验边界

继续使用此前的 100 ps 工程假设做有界试验，目的是判断少量延迟修复能否让
新半拍网表在该假设下同时满足 setup/hold。该数值尚没有实测时钟抖动、时钟树
偏斜或最终实现的数据支撑；正式验收必须明确工程假设及适用范围。
时钟 uncertainty 建模的工具语义参考 Synopsys《Timing Constraints and
Optimization User Guide》U-2022.12 的 Clock Uncertainty 章节：
[手册镜像](https://studylib.net/doc/27622832/synopsys%C2%AE-timing-constraints-and-optimization-user-guide)。

- 保留原 run、RTL、已通过的功能结果、1 ns SDC 和 compiled DDC，不覆盖。
- 新建 `hold_pilot_<时间>_<随机>/`，只读取本轮半拍版的原始 compiled DDC。
- 显式把内存中 hold uncertainty 设为 0.10 ns，setup 仍为 1 ns，IO 预算不变。
- 应用预算后检查 setup WNS 未变化，再执行真实的增量 hold 优化。
- 保留所有库时序检查。优化前后比较序列化 SDC 的时序预算，禁止额外改预算。
- 不重复 VCS 或 Library Compiler，不重做 RTL 综合；DC 上限 1200 秒，退出宽限 30 秒。
- 成功仍标记为 `PILOT_COMPLETE`，原 1 ns 约束的 FAIL 保留。

## 运行入口

上传包 `kwt_phase_hold_pilot_20261030.tar.gz` 只包含工具、综合脚本和说明。
不含官方库、旧网表或新 RTL。服务器执行：

```bash
mkdir -p ~/soc/kwt_phase_hold_pilot_20261030
tar -xzf ~/Desktop/kwt_phase_hold_pilot_20261030.tar.gz -C ~/soc/kwt_phase_hold_pilot_20261030
bash ~/soc/kwt_phase_hold_pilot_20261030/tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261030_161124_* --phase-pilot 0.10
```

入口要求原 run 四组功能测试通过、输入 SHA256 未变化、真实库新综合完成、
宏时钟及写路径的四项 setup/hold 摘要都非负，并存在本轮原始检查点。
不接受旧同沿 run，也不从此前的 hold pilot 网表继续优化。

输出保留 `ORIGINAL_HOLD_STATUS: FAIL`、试验预算、优化前后报告及修复网表。
只有面积预算、全局 setup、全局 hold、宏时钟及写路径的四项检查全部通过，
才能报告本试验通过；失败、缺少检查、检查点被改变或超时均报失败。
本地验证了脚本和状态判定；服务器本轮试验通过，数值及适用范围见本文开头。
