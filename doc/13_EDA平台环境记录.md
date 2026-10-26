# EDA 平台环境记录

> 2026-10-26 实测。下次上机照着做，不必重新摸索。

## 1. 账号与接入

| 项 | 值 |
|---|---|
| 服务器 | 1 号机，主机名 `RDserver01` |
| home | `/storage1/2026contest/server1/s1_12usr` |
| 用户名 | `s1_12usr` |
| VNC | `ic1h22.nicu.cn:15912`（RealVNC Viewer，地址栏直接填，`:15912` 按端口解析） |
| FTP | `icdesigns0.nicu.cn:18888`（说明：根目录是 `~/Desktop`，见 §3） |

- VNC 默认密码 `Asdf@26#`，用 `vncpasswd` 改；**只认前 8 位**，超出部分忽略
- Linux 密码用 `yppasswd` 改（**不是 `passwd`**），FTP 用的就是它
- ⚠️ **绝不能点 Logout** —— 注销后无法再登录，需管理员介入。不用了就关窗口，会话保留
- VNC 画质按 `F8` → Properties 调整，**禁用 High**（占带宽且画质无改善）

## 2. EDA 工具链

工具统一装在 `/eda`，普通用户可执行不可改。

| 类别 | 工具 | 路径 |
|---|---|---|
| 综合 | `dc_shell` **2022.03-SP5** | `/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell` |
| 综合（备选） | `genus` | `/eda/cadence/genus` |
| 仿真 | `vcs` **2020.03-SP2-6** | `/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs` |
| 仿真（备选） | `vsim` (QuestaSim) | `/eda/mentor/questasim` |
| 调试 | `verdi` **2020.03-SP2-6** | `/eda/synopsys/verdi/verdi_2020.03-SP2-6/bin/verdi` |
| 时序 | `pt_shell` | 已配置在 PATH |
| 形式验证 | `fm_shell` | 已配置在 PATH |
| 版图 | `innovus`、`icc2`、`calibre` | — |
| HLS | `catapult_synthesis` | `/eda/mentor/` |
| FPGA | `vivado` 2021.1 | `/eda/xilinx/vivado2021.1` |

- 默认 shell 是 **tcsh**，环境变量在 `~/.cshrc`
- **写脚本前先敲 `bash`** —— tcsh 不支持 `2>&1`（报 `Ambiguous output redirect`）

## 3. FTP 的坑（重要）

**数据端口不稳定，必须重试。**

现象：控制连接（18888）永远能通，认证也能过，但 `LIST`/`STOR` 时服务器返回的被动端口（18xxx）经常超时。

结论：服务器可能只在校内网放行完整的被动端口范围，公网只开了控制端口。主动模式（`PORT`）被服务器禁用（回 530）。

**可用做法**：本地 PowerShell 循环重试，通常第 2~6 次成功。

```powershell
$pw = Read-Host "FTP password" -AsSecureString
$p  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
         [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
for ($i=1; $i -le 8; $i++) {
    Write-Host "attempt $i ..."
    curl.exe -s -T release/rtl.tar.gz `
        "ftp://icdesigns0.nicu.cn:18888/rtl.tar.gz" `
        --user "s1_12usr:${p}" --connect-timeout 12 --max-time 300
    if ($LASTEXITCODE -eq 0) { Write-Host "UPLOAD OK"; break }
}
```

**其他注意事项**

- **FTP 登录后的根目录是 `~/Desktop`**，不是 `~`。传上去的文件要先 `mv ~/Desktop/xxx ~/`
- **只能上传，不能下载**
- 带宽限制 200 KB/s，支持断点续传，大文件建议夜间传
- **不要用 `curl -v`** —— 它会把 `> PASS <密码>` 明文打到终端

## 4. VNC 剪贴板与终端输入

- 剪贴板同步依赖服务器端的 `vncconfig` 进程，断了就粘贴不了。断开后重跑：
  ```
  vncconfig -nowin &
  ```
- **粘贴会吃掉命令的第一个字符** —— 粘贴前先敲一个空格
- **粘贴会在 `&` 前后插入空格**，导致 `2>&1` 变成 `2> &1`。避免使用 `&` 和重定向，或改用 `;` 分隔
- `grep` 的模式里有 `|` 时必须用多个 `-e` 参数（引号容易被粘贴吞掉）：
  ```
  grep -i -e smic -e tsmc      # 而不是 grep -iE "smic|tsmc"
  ```

## 5. 标准单元库：未发放

**2026-10-26 实测确认缺失。**

- `find /eda -name "*.db"` 只找到 Synopsys 工具自带的通用库（`gtech.db`、`fpga.db`、`class.lib`、ICC2 的 help 库等）
- `find /eda -maxdepth 3 -type d | grep -i -e smic -e tsmc -e saed -e gpdk -e std -e libcell` **无匹配**
- `/eda/other/amazeFP` 是**工具**（含 `bin`/`etc`/`tools`/`Admin_amazefp_install_file`/`amazefp_lic_file`），**不是工艺库**；`e22` 是版本号不是 22nm

**影响**：面积、150 MHz 时序、功耗全部无法评估，任务 7 只能等库。

## 6. 已完成的验证（2026-10-26）

代码已上传至 `~/rtl`（21 文件）、`~/tb`（18 文件）、`~/sim/vectors`（93 文件）。

VCS 编译命令：

```bash
cd ~
vcs -full64 -sverilog -timescale=1ns/1ps -o simv_top rtl/*.v tb/tb_kwt_top.v
cd ~/sim && ../simv_top        # tb 用 vectors/... 相对路径，必须在 ~/sim 下跑
```

结果：

| TB | 结果 |
|---|---|
| `tb_kwt_linear` | `cycles=6339  outputs=6336/6336  errors=0` PASS |
| `tb_kwt_top` | `cycles=1591853 (10.61 ms @150MHz)`，3/3 样本分类正确 PASS |

**与本地 Vivado xsim 结果逐位一致**（周期数、分类结果、内部数值全对上），VCS 跑完整机仿真仅 32 秒 CPU 时间。

这是「可复现工程」的硬证据：RTL 不依赖特定仿真器。

## 7. 待办

1. 向组委会申请标准单元库与 SRAM 宏（16b×128 / 16b×1024 / 16b×4096 的面积与时序模型）
2. 库到手后：`dc_shell` 综合 → 面积/时序 → 决定寄存器数组 SRAM 化的改造范围
3. 反馈 FTP 数据端口问题
