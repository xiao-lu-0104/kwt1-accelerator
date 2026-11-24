# AXI-4 Lite 从机寄存器映射

`rtl/kwt_axi_slave.v` 把 KWT-1 加速器包装成一个 AXI4-Lite 从设备，便于挂到
E203 / 任何 RISC-V 总线上。数据宽度 32 位，地址宽度可参数化（默认 16 位足够）。

## 1. 寄存器表

| 偏移 | 名称 | 访问 | 说明 |
|---|---|---|---|
| `0x000` | `CTRL` | W | bit0 `start`（写 1 触发一次推理，自清零）；bit1 `soft_rst`（软复位） |
| `0x004` | `STATUS` | R | bit0 `busy`；bit1 `done` |
| `0x008` | `PRED` | R | `[3:0]` 最近一次推理的分类结果（0..11） |
| `0x00C` | `CYCLES` | R | 最近一次推理的周期数 |
| `0x010` | `NFRAMES` | R | 已写入的 MFCC 字数（每字 4 字节） |
| `0x100 + 4*i` | `MFCC` | W | MFCC 特征写入窗口，第 `i` 个字（`i = 0..979`） |
| `0x800 + 4*i` | `ACT` | R | 激活值读回窗口，`i = 0..1583`，`act_rd_addr = i`（11 位） |

## 2. 一次推理的软件流程

```c
// 1. 清软复位
write32(KWT_BASE + 0x000, 0x2);
write32(KWT_BASE + 0x000, 0x0);

// 2. 写 980 个 MFCC 字（98 帧 x 40 字节 = 3920 字节，补零到 3920）
for (i = 0; i < 980; i++)
    write32(KWT_BASE + 0x100 + 4 * i, mfcc_words[i]);

// 3. 触发
write32(KWT_BASE + 0x000, 0x1);

// 4. 轮询
while (!(read32(KWT_BASE + 0x004) & 0x2))
    ;

// 5. 读结果
pred   = read32(KWT_BASE + 0x008) & 0xF;
cycles = read32(KWT_BASE + 0x00C);
```

## 3. MFCC 字节序

一个字承载 4 个连续 MFCC 字节，**小端**：`word[7:0]` 是最低地址的字节。
`mfcc_addr = (byte_addr >> 2)`，`byte_addr = frame * 40 + coef`。

## 4. 与 `kwt_top` 的连接

```
kwt_axi_slave                    kwt_top
  mfcc_we/mfcc_addr/mfcc_data --> s_mfcc_we / s_mfcc_addr / s_mfcc_data
  start                       --> start
  busy                        <-- busy
  done_in                     <-- done
  pred                        <-- pred
  cycles                      <-- cycle_count
  act_rd_addr/act_rd_data     <-- out_buf 读口
```

`kwt_axi_top` 已把 AXI 从机与计算顶层连接起来。32 位 MFCC 字经四字节并行写入
输入缓冲，按 40 字节特征行映射到 64 字节 token stride，未使用的 24 通道保持
不写；ACT 读窗口接到顶层输出缓冲。忙状态由启动/完成握手跟踪，CTRL 软复位接到
计算顶层复位。patch、class/position、分类头参数以及编码器参数 ROM 仍由 SoC/平台
侧提供，因此这是加速器接口集成壳，不是完整 E203 SoC 集成。

MFCC 写窗口为 `0x0100..0x104f`，最后一个对齐字地址 `0x104c`；ACT 读窗口为
`0x0800..0x20bf`，最后一个对齐字地址 `0x20bc`。两者地址重叠但读写方向不同。
MFCC 仅支持对齐的全字写；部分字节写返回 SLVERR，零 strobe 写为无操作。
CTRL 仅在 `wstrb[0]` 有效时更新，软复位同时清零写入计数。
计数反映写事务数，不验证各地址是否已完整装载。

## 5. 验证

`sim/` 下：

```powershell
xvlog -sv ..\rtl\kwt_axi_slave.v ..\tb\tb_kwt_axi_slave.v
xelab tb_kwt_axi_slave -s axi_snap --debug typical
xsim axi_snap -R
```

期望输出 `PASS: AXI4-Lite slave, all registers behave`，覆盖：

- MFCC 写入落到正确地址（`mfcc_addr` 递增、`NFRAMES` 计数正确）
- `STATUS` 的 `busy` / `done` 位随输入实时变化
- `PRED`、`CYCLES`、`ACT` 窗口读回值正确
- `CTRL.start` 写入后产生单拍脉冲
- `tb_kwt_axi_top_load` 通过 AXI 写事务检查输入字到计算核缓冲区的映射

## 6. 时序说明

读通道采用三级流水（`S_R_IDLE → S_R_CALC → S_R_DATA`），保证 `rdata` 在
`rvalid` 有效时已经稳定，避免组合读延迟导致的采样错误。写通道为
`S_W_IDLE → S_W_DATA → S_W_RESP` 三段，`awready` 与 `wready` 分时有效，
主机需分别等待两个握手（AXI 规范允许这种实现）。
