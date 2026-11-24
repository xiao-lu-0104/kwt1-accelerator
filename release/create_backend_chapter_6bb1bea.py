from pathlib import Path
from docx.shared import Inches,Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Reuse the verified type and table formatting; retain the previous report.
source=Path('release/create_dc_word_6bb1bea.py').read_text(encoding='utf-8')
exec(source.split("doc.add_paragraph('DC综合与功耗评估', 'Title')")[0])
OUT=ROOT/'doc/提交/后端流程与结果_6bb1bea_待补FFN与功耗.docx'
doc.styles['Heading 2'].font.size=Pt(11.5)
doc.styles['Heading 2'].paragraph_format.space_before=Pt(7)

def code(s):
    p=doc.add_paragraph()
    p.paragraph_format.space_after=Pt(6)
    p.paragraph_format.line_spacing=Pt(11.5)
    for i,line in enumerate(s.strip('\n').splitlines()):
        if i:p.add_run('\n')
        r=p.add_run(line);r.font.name='Consolas';r.font.size=Pt(9)
        r._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体')
    return p

doc.add_paragraph('后端流程与结果','Title')
para('本章介绍逻辑综合与功耗分析流程，对比仅实现本科必做第 1—3 项的独立 FFN 配置与包含选做功能的完整加速器配置，并给出关键脚本及服务器复现入口。两种配置分别固定源码和参数，各自的面积、时序、性能及功耗保持一致。')
doc.add_paragraph('1  后端流程','Heading 1')
doc.add_paragraph('1.1  DC逻辑综合','Heading 2')
para('采用 Synopsys Design Compiler 2022.03-SP5-5，在 SMIC 40 nm RVT、TT、1.1 V、25 ℃条件下进行综合。读取 RTL 和指定标准单元、SRAM 宏库，完成展开、链接与工艺映射；目标时钟为 150 MHz，时钟周期为 6.666667 ns。保留设计层次，主综合后按需进行增量 hold 优化，导出 DDC、Verilog 网表、SDC 及面积和时序报告。')
doc.add_paragraph('1.2  功耗分析','Heading 2')
para('功耗采用对应配置的门级任务活动 SAIF 标注到同版本 DDC。冷任务窗口覆盖参数及输入装载、调度、计算和最终结果写回；逐字比对黄金输出后生成活动文件。以相同工艺角、频率和接口负载估计内部、开关及漏电功耗，分别报告加速器分项和系统总功耗，单任务能耗为平均功耗乘以任务时间。系统统计覆盖 E203、互连、加速器、共享及私有 SRAM 和 TCM。')
doc.add_paragraph('2  综合与功耗结果','Heading 1')
para('独立 FFN 配置仅保留必做前馈线性计算及其装载、写回和接口逻辑；完整配置为 6bb1bea、16 MAC，含 56 个 RAMSP1024X16 私有 SRAM，共 112 KiB。下表区分两种配置，不将完整设计的模块面积相减作为独立 FFN 的综合结果。')
table(['面积统计对象','面积 / mm²','结果范围'],[
    ['独立 FFN 配置','待独立综合','必做第 1—3 项及所需接口、私有 SRAM'],
    ['完整加速器已综合部分','0.846539','逻辑及接口 0.334222；私有 SRAM 0.512317'],
    ['完整加速器新增硬件合计','待补仲裁器面积','上述已综合部分加新增 CPU/DMA 仲裁器'],
], [2.1,1.3,3.5])
para('完整加速器已综合边界的 setup WNS 为 +0.197581 ns，hold WNS 为 +0.00112969 ns，均满足所声明的时序约束。复用 CPU、共享 SRAM 和固定平台逻辑不计入加速器面积；完整系统映射单元面积另列为 3.081792 mm²。该系统数值不作为加速器面积，亦不用于宣称完整系统时序收敛。')
table(['配置与任务','加速器功耗\n/ mW','系统功耗\n/ mW','时间 / ms\n能耗 / μJ'],[
    ['独立 FFN 配置  FF1 冷任务','待测','待测','待测'],
    ['完整配置  Encoder 单层冷任务','待测','待测','待测'],
], [2.65,1.25,1.25,1.75])
p=doc.add_paragraph('完整配置运行 FF1 的功耗另作补充对照，不能代替独立 FFN 配置的功耗。完整十二层任务如需单列，须取得其自身活动与计时结果。当前功耗均留待实测填写。')
for r in p.runs:r.font.size=Pt(10)

p=doc.add_paragraph('3  关键脚本','Heading 1')
p.paragraph_format.page_break_before=True
para('以下摘录当前脚本的核心命令；库路径、源文件清单和约束文件由 Config.tcl 绑定。FFN 独立配置应使用单独顶层和源清单，沿用同一工艺及约束条件。')
doc.add_paragraph('3.1  综合映射与报告','Heading 2')
code('''source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
set_host_options -max_cores 4
define_design_lib WORK -path work
analyze -format sverilog -define $Defines $Sources
elaborate $Top
current_design $Top
link
source $ConstraintFile
compile_ultra -no_autoungroup -no_boundary_optimization
# 如需修复 hold，在本轮基线 DDC 上增量执行
set_fix_hold [get_clocks CoreClock]
compile -incremental_mapping -only_hold_time
write -hierarchy -format ddc -output candidate.ddc
write -hierarchy -format verilog -output candidate.v
write_sdc -nosplit candidate.sdc
redirect area.rpt {report_area -hierarchy}
redirect setup.rpt {report_timing -delay_type max -max_paths 20}
redirect hold.rpt {report_timing -delay_type min -max_paths 20}''')
doc.add_paragraph('3.2  时序约束与功耗标注','Heading 2')
code('''# Constraints.tcl 核心时钟约束
create_clock -name CoreClock -period 6.666667 [get_ports Clock]
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]

# Power.tcl 核心功耗流程
source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
saif_map -start
read_ddc $SystemDdc
current_design SystemPhysical
link
reset_switching_activity -all
read_saif -input $ActivityFile -instance_name PowerTest/Dut \\
    -auto_map_names
redirect power.rpt {report_power}
redirect power_hierarchy.rpt {report_power -hierarchy}
redirect saif_hierarchy.rpt {report_saif -hierarchy}
redirect saif_missing.rpt {report_saif -hierarchy -missing}''')
para('Power.tcl 按层次拆分 ACCELERATOR、CPU_BUS、SHARED_SRAM、TCM 与 OTHER，检查分项与系统总功耗的一致性，并保留活动覆盖率报告。门级活动采用零延迟条件；当前初始化策略仅在首个复位时钟施加明确二态触发器初值，任务开始前永久释放，结果须注明该适用条件。')

p=doc.add_paragraph('4  服务器复现命令与文件','Heading 1')
p.paragraph_format.page_break_before=True
para('服务器采用离线脚本传输，不依赖 FTP 或服务器访问 GitHub。源码固定为 6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6；以下为当前完整加速器的复现入口。独立 FFN 配置的提交、脚本和结果目录待该配置冻结后补充，不能直接沿用完整配置结果。')
doc.add_paragraph('4.1  运行与查看结果','Heading 2')
code('''# 已通过 pluma 安装脚本及库缓存后，在服务器终端执行
bash ~/Desktop/RunNewDc_6bb1bea.sh
bash ~/Desktop/RunPower_6bb1bea.sh

# 当前工作目录及已完成综合报告
U=$(id -u)
D=/tmp/final_dc_6bb1bea_$U
P=/tmp/final_power_6bb1bea_$U
cat "$D/hold_accelerator/Metrics.tsv"
cat "$D/hold_accelerator/area.rpt"
cat "$P/system/Metrics.tsv"

# 功耗完成后查看；文件未生成时不作为已有结果
cat "$P/PowerSummary.json"
cat "$P/ff1/power/power.rpt"
cat "$P/encoder/power/power.rpt"''')
para('首次传输使用 pluma ~/Desktop/脚本名.sh 打开服务器编辑器，在本机运行对应 PowerShell 剪贴板入口，粘贴并保存后执行。长脚本可用 -Part 分段追加。当前二态启动扩展 ResumePowerBinary_6bb1bea.sh 仅安装一次，后续使用 RunPower_6bb1bea.sh 继续流程。')
p=doc.add_paragraph(r'本机传输入口位于 E:\chipdesign\release：newdc_6bb1bea\CopyNewDcToClipboard.ps1，以及 newpower_6bb1bea 下的 CopyPowerToClipboard.ps1、CopyBinaryRecoveryToClipboard.ps1。')
for r in p.runs:r.font.size=Pt(10)
table(['文件或目录','内容'],[
    ['$D/source/','固定版本 RTL、Backend、Sim 及软件源文件'],
    ['$D/tools/Dc.tcl\n$D/integration/Constraints.tcl','综合流程及本轮时序约束'],
    ['$D/hold_accelerator/','candidate.ddc、candidate.v、candidate.sdc、面积与时序报告'],
    ['$P/tools/','System.tcl、Power.tcl、PowerTest.sv、RunPower.py 及初始化脚本'],
    ['$P/system/','完整系统 DDC、网表、Metrics.tsv 和层次叶单元清单'],
    ['$P/ff1/  与  $P/encoder/','TaskMetrics.tsv、task.saif、Activity.json；power/ 保存功耗报告'],
    ['/tmp/final_7cf5155_pdk_$U/','复用工艺库缓存及 Pdk.json；不随新提交号改名'],
], [3.15,3.75])
p=doc.add_paragraph('复现条件：保留上述 /tmp 目录与对应版本脚本。当前服务器 UID 为 11012；$D、$P、$U 为本页命令定义的变量。归档提交时须同时保存源码、库路径清单、配置、网表、约束、活动及原始报告，避免依赖临时目录长期存在。')
for r in p.runs:r.font.size=Pt(10)
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=footer.add_run('6bb1bea  ·  独立 FFN 与功耗结果待补');r.font.size=Pt(9)
for root in [doc.styles.element,doc.element]:
    for el in list(root.iter(qn('w:pBdr'))):el.getparent().remove(el)
doc.core_properties.title='后端流程与结果'
doc.core_properties.subject='本科必做独立FFN与完整加速器对比章节'
doc.save(OUT)
print(OUT)
