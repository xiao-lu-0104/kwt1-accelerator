# SRAM hold 恢复：v5

适用于 `tpusoc_88e529e_single_20261102_v4` 的已完成服务器运行。
用户确认优先修复 SRAM 写数据入口约 -0.120269 ns 的 hold，不优化 CPU setup。

运行已上传的单文件脚本：

```bash
bash ~/Desktop/tpusoc_sram_hold_20261102_v5.sh --run-dir ~/soc/tpusoc_single_20261102_171803_*
```

脚本核对 v4 原源码清单、已通过的宏测试标记及原标准单元/SRAM DB 哈希，
将 E203TpuBackend_mapped.ddc 复制到新的 sram_hold_20261102_* 子目录。
原映射 DDC 与库保持只读，完成后再次核对哈希。

从 DDC 继承全部原时序要求；不重建时钟、不改 uncertainty、IO delay、例外或周期。
冻结 `Tpu/Core/Sram` 层级外的单元及兄弟层级，保留全部 56 个真实宏。
执行一次 `set_fix_hold` 加 `compile -incremental_mapping -only_hold_time`，
整个 DC 调用限时 600 秒。不会重新分析 RTL，不运行修复循环。
命令依据是 [Synopsys Design Compiler User Guide T-2022.03（镜像）](https://studylib.net/doc/27191936/dcug)
的 hold-only compile 与 dont_touch 小节；该版本明确只有 compile 支持 only_hold_time。

修复后保存独立候选 DDC、网表和 SDC，比较前后完整有效 SDC 行
（只排除 set_fix_hold、set_dont_touch 优化属性），并核对层级外叶单元名称和库引用。
这些检查不等于形式等价验证。即便候选未达到接受条件，也不覆盖原工程。

`hold_result.txt` 给出前后 setup、hold、SRAM 输入 hold 及库单元面积。
HOLD_REPAIR_STATUS 只有在全局 setup、hold 和 SRAM 输入 hold 都非负时才 PASS。
REPORTS_COMPLETE 仅表示流程完成；脚本未执行前不能声称修复有效。
所有时序结论限于 TT 综合模型，物理 hold 仍需 CTS、寄生参数和多角分析。

本地验证覆盖策略范围、例外变化检测、层级外单元变更检测、原输入哈希和损坏文件拒绝。
本地没有 Synopsys DC，实际优化效果和运行兼容性以服务器日志为准。

## v5 已执行后的只读补报

服务器 v5 优化完成且保存候选，但在层级外叶单元数量检查处退出。
先不要重跑 v5；执行单文件 v5b 补报：

```bash
bash ~/Desktop/tpusoc_sram_hold_report_20261102_v5b.sh --recovery-dir ~/soc/tpusoc_single_20261102_171803_*/sram_hold_20261102_*
```

v5b 分别读取私有原始 DDC 和已保存候选 DDC，不 compile、不写网表。
先生成时序报告，再逐项比较层级外单元，分别列真实单元与 **logic_0/1** 工具伪单元。
`TIMING_REPAIR_STATUS` 表示固定约束下的 TT 时序结果；
若有任何层级外差异，`CANDIDATE_REVIEW` 保持待审，完整明细在 `outside_changes.tsv`。
不会仅因伪单元差异就声称功能等价，也不会因差异挡住时序结果。
原始和候选 DDC、库输入在补报前后均核对哈希。

服务器 v5b 已回传：hold 从 -0.120269 ns 改善到 +0.00112969 ns，
setup 保持 +0.000449181 ns，时序约束不变。
层级外有 18 项真实单元变化，CPU 叶单元名称/库引用变化 0 项。
完整清单现已核对：Tpu/Core/U739 至 U750 为 12 个 BUFV32RQ_12TR40，
U751 至 U754 为 4 个 BUFV32_12TR40，U755 至 U756 为 2 个 BUFV24RQ_12TR40。
全为新增 buffer，无原有层级外单元删除或替换。它们位于 SRAM 父层级，
超出原范围校验的路径前缀，因此触发 v5 数量保护。
清单类型核对完成，服务器原 PENDING 标记作为历史原样保留；
当前记录为 TT 综合时序 PASS，不标为形式等价或物理签核。
后续使用恢复目录下 E203TpuBackend_hold_candidate.ddc/.v/.sdc；
RTL 没有包含这些网表缓冲，重新综合时须重现 hold 修复。
