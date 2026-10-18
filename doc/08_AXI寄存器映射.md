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
| `0x800 + 4*i` | `ACT` | R | 激活值读回窗口，`act_rd_addr = (0x800 + 4*i) >> 2` |

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

`kwt_top` 现有的 `s_mfcc_*` 端口正好是 32 位字接口，因此 MFCC 窗口可以直连，
不需要额外的打包逻辑。

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

## 6. 时序说明

读通道采用三级流水（`S_R_IDLE → S_R_CALC → S_R_DATA`），保证 `rdata` 在
`rvalid` 有效时已经稳定，避免组合读延迟导致的采样错误。写通道为
`S_W_IDLE → S_W_DATA → S_W_RESP` 三段，`awready` 与 `wready` 分时有效，
主机需分别等待两个握手（AXI 规范允许这种实现）。
