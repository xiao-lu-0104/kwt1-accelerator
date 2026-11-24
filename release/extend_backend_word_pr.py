from pathlib import Path
from copy import deepcopy
import hashlib,json,math,shutil
from PIL import Image,ImageDraw,ImageFont
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path('E:/chipdesign')
SRC=ROOT/'doc/提交/后端流程与结果_6bb1bea_待补FFN与功耗.docx'
OUT=ROOT/'doc/提交/后端流程与结果_含历史PR_修订版.docx'
QA=ROOT/'release/backend_pr_word_qa';QA.mkdir(exist_ok=True)
backup=QA/'用户修改原稿.docx'
if not backup.exists():shutil.copy2(SRC,backup)
original_hash=hashlib.sha256(SRC.read_bytes()).hexdigest()
doc=Document(SRC)
original_paragraphs=[p.text for p in doc.paragraphs]
orig=doc.paragraphs[:]
tables=doc.tables[:]
assets=ROOT/'doc/提交/后端设计与评估报告_1110版/assets'

def pbefore(anchor,text='',style=None,code=False):
    p=doc.add_paragraph(text,style)
    anchor.addprevious(p._p)
    if code:
        p.paragraph_format.line_spacing=Pt(11.5)
        for r in p.runs:r.font.name='Consolas';r.font.size=Pt(9)
    elif style is None:
        p.paragraph_format.first_line_indent=Pt(22)
    return p

def h(anchor,text,level=2,page=False):
    p=pbefore(anchor,text,'Heading '+str(level));p.paragraph_format.page_break_before=page
    return p

def caption(anchor,text):
    p=pbefore(anchor,text)
    p.paragraph_format.first_line_indent=Pt(0);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after=Pt(8)
    for r in p.runs:r.font.size=Pt(10)
    return p

def picture(anchor,path,width,cap):
    p=pbefore(anchor)
    p.paragraph_format.first_line_indent=Pt(0);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next=True
    p.add_run().add_picture(str(path),width=Inches(width))
    caption(anchor,cap)

def format_table(t,widths=None):
    t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    if widths is None:widths=[6.9/len(t.columns)]*len(t.columns)
    for col,w in zip(t.columns,widths):col.width=Inches(w)
    for i,row in enumerate(t.rows):
        for j,c in enumerate(row.cells):
            c.width=Inches(widths[j]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            pr=c._tc.get_or_add_tcPr()
            for old in list(pr.findall(qn('w:tcBorders'))):pr.remove(old)
            borders=OxmlElement('w:tcBorders')
            for edge in ('top','bottom','left','right'):
                e=OxmlElement('w:'+edge)
                for k,v in [('val','single'),('sz','4'),('color','D9D9D9')]:e.set(qn('w:'+k),v)
                borders.append(e)
            pr.append(borders)
            margin=OxmlElement('w:tcMar')
            for side in ('top','bottom','left','right'):
                e=OxmlElement('w:'+side);e.set(qn('w:w'),'90');e.set(qn('w:type'),'dxa');margin.append(e)
            pr.append(margin)
            if i==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E7EDF3');pr.append(sh)
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.05
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 else WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:r.font.size=Pt(10.5);r.bold=i==0
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))

def table(anchor,headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));anchor.addprevious(t._tbl)
    for c,s in zip(t.rows[0].cells,headers):c.text=s
    for row in rows:
        for c,s in zip(t.add_row().cells,row):c.text=s
    format_table(t,widths)
    spacer=pbefore(anchor);spacer.paragraph_format.line_spacing=Pt(2);spacer.paragraph_format.space_after=Pt(4)
    return t

def flow(path,steps,subtitle):
    im=Image.new('RGB',(2100,1050),'white');dr=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',44)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',34)
    xs=[60,760,1460];ys=[110,430,750]
    positions=[(xs[i],ys[0]) for i in range(3)]+[(xs[i],ys[1]) for i in (2,1,0)]+[(xs[i],ys[2]) for i in range(3)]
    w,hh=580,170
    def arrow(a,b):
        dr.line([a,b],fill='#526273',width=5)
        angle=math.atan2(b[1]-a[1],b[0]-a[0]);l=22
        points=[b,(b[0]-l*math.cos(angle-.5),b[1]-l*math.sin(angle-.5)),(b[0]-l*math.cos(angle+.5),b[1]-l*math.sin(angle+.5))]
        dr.polygon(points,fill='#526273')
    for i,(title,detail) in enumerate(steps):
        x,y=positions[i]
        dr.rounded_rectangle((x,y,x+w,y+hh),radius=14,fill='#EEF3F7',outline='#8899AA',width=3)
        dr.text((x+24,y+25),str(i+1)+'  '+title,font=font,fill='#152331')
        dr.text((x+24,y+95),detail,font=small,fill='#35485A')
        if i:
            px,py=positions[i-1]
            if y==py:
                a=(px+w,py+hh/2) if x>px else (px,py+hh/2)
                b=(x,y+hh/2) if x>px else (x+w,y+hh/2)
            else:a=(px+w/2,py+hh);b=(x+w/2,y)
            arrow(a,b)
    dr.text((65,20),subtitle,font=small,fill='#35485A')
    im.save(path,dpi=(300,300))

flow(QA/'dc_flow.png',[
 ('固定输入与参数','RTL 版本  顶层  MAC配置'),('配置工艺与宏库','标准单元 DB  SRAM DB'),('分析与展开','analyze  elaborate  link'),
 ('加载时序约束','150 MHz  IO预算  不确定度'),('工艺映射综合','compile_ultra  保留层次'),('保存基线并分析','baseline DDC  setup / hold'),
 ('按需增量优化','保持时间修复  重新报告'),('冻结候选结果','网表  DDC  SDC  面积'),('交付活动分析输入','同版本系统映射与 SAIF')],
 'DC 综合流程  实际脚本按时序检查结果决定是否执行增量 hold 优化')
flow(QA/'pr_flow.png',[
 ('载入旧版综合结果','707cd7f  系统网表与 SDC'),('绑定物理与 RC 库','RVT / SRAM NDM  TYP RC'),('芯核 宏及 IO 规划','45%利用率  分组端口'),
 ('宏固定与单元合法化','keepout  标准单元放置'),('电源网络生成','ring  mesh  rails  宏连接'),('时钟树构建','clock_opt build_clock'),
 ('时钟网络布线','clock_opt route_clock'),('信号网络布线','route_auto  保存检查点'),('导出与检查归档','nlib  DEF  GDS  报告')],
 '历史 PR 流程  已完成基础实现与导出  未执行完整 place_opt / final_opto / 独立 route_opt')

# Add to the user's own wording; do not recreate the source chapter.
anchor=orig[5]._p
pbefore(anchor,'DC 流程以冻结 RTL、宏库和约束为统一输入，各阶段使用同一 16 MAC 参数。宏实例按实际容量与数据位宽映射到指定 SRAM 单元，逻辑部分映射到 RVT 标准单元。综合前声明目标时钟及接口预算，使面积和时序结果对应明确的外部工作条件。')
picture(anchor,QA/'dc_flow.png',6.8,'图1  DC综合及结果冻结流程')
pbefore(anchor,'主综合完成后先保存基线，再读取建立时间和保持时间路径；需要修复保持时间时，从本轮基线启动增量映射。候选结果同时保留网表、SDC 和层次面积报告，避免只记录某个总面积数值而丢失其配置与约束来源。完整系统活动分析直接读取该候选，不以其他版本网表替代。')
anchor=orig[7]._p
pbefore(anchor,'任务活动的采集边界与任务计算边界一致。SAIF 记录期间既包含乘加单元的运算，也包含 CPU 驱动、握手等待、数据搬运和输出写回；最终写响应完成后结束计时。功耗分析按同一窗口统计系统与加速器分项，内部功耗、开关功耗和泄漏功耗分别保留，便于解释平均功耗和单任务能耗之间的关系。')
pbefore(anchor,'活动生成首先检查任务输出、有效访问地址、写掩码与数据是否已知，再核对 SAIF 的时间尺度和持续时间。SAIF 与当前 DDC 完成层次映射后，输出分组功耗以及缺失活动报告；对于使用默认或传播活动的对象保留其实际覆盖情况，不以空闲活动代替有效任务负载。')
h(anchor,'1.3  PR布局布线')
pbefore(anchor,'除当前版本的逻辑综合与功耗工作外，我们还在先前 707cd7f 版本上完成了 ICC2 基础布局布线。该版本包含 64 MAC 加速器及 E203 集成系统，已执行芯核规划、SRAM 宏布局、分组 IO 放置、电源网络生成、时钟树构建、时钟布线与信号布线，并导出原生设计库、DEF、Verilog、SDC 和 GDSII。')
pbefore(anchor,'PR 使用 Synopsys IC Compiler II T-2022.03-SP2-1，物理库与综合库采用相同 SMIC 40 nm 工艺体系。通过分阶段保存设计检查点，将芯核规划、供电、时钟和信号连接组织成可接续的物理实现流程；最终归档在持久盘解包后重新绑定参考库，并已成功打开最终版图。该成果用于展示已有物理实现工作，与本轮 6bb1bea 的综合及功耗结果分别列示。')

# Keep the edited two-column area table verbatim; make timing equally tabular.
orig[7].paragraph_format.page_break_before=False
h(tables[0]._tbl,'2.1  面积结果')
caption(tables[0]._tbl,'表1  两种设计范围的综合面积')
format_table(tables[0],[4.6,2.3])
timing=orig[10]
timing.text='复用 CPU、共享 SRAM 和固定平台逻辑不计入加速器面积；'
anchor=timing._p
h(anchor,'2.2  时序结果')
caption(anchor,'表2  当前版本加速器综合时序')
table(anchor,['统计对象','指标','结果','判定'],[
 ['完整加速器已综合边界','目标频率','150 MHz','约束输入'],
 ['完整加速器已综合边界','时钟周期','6.666667 ns','约束输入'],
 ['完整加速器已综合边界','Setup WNS','+0.197581 ns','满足所声明约束'],
 ['完整加速器已综合边界','Hold WNS','+0.00112969 ns','满足所声明约束'],
 ['独立 FFN 配置','Setup / Hold','待独立综合','待测'],
], [2.5,1.3,1.5,1.6])
anchor=tables[1]._tbl
h(anchor,'2.3  功耗与能耗结果')
caption(anchor,'表3  冷任务窗口的平均功耗与单任务能耗')
old_power=[[c.text for c in r.cells] for r in tables[1].rows]
for i,row in enumerate(tables[1].rows):
    if i==0:
        row.cells[3].text='任务时间\n/ ms'
    else:row.cells[3].text='待测'
tables[1].add_column(Inches(1.2))
tables[1].rows[0].cells[4].text='系统能耗\n/ μJ'
for row in tables[1].rows[1:]:row.cells[4].text='待测'
ff1=tables[1].add_row()
for c,s in zip(ff1.cells,['完整配置  FF1 冷任务','32.622239','41.293946','1.449860','59.870452']):c.text=s
# Keep both complete-configuration workloads next to each other.
tables[1]._tbl.remove(ff1._tr)
tables[1].rows[1]._tr.addnext(ff1._tr)
for row in tables[1].rows:
    if row.cells[0].text=='完整配置  Encoder 单层冷任务':
        for c,s in zip(row.cells,['完整配置  Encoder 单层冷任务','33.240223','41.687711','4.797434','199.994055']):c.text=s
format_table(tables[1],[2.7,1.1,1.1,1,1])
orig[12].text=orig[12].text.replace('当前功耗均留待实测填写。','当前完整配置的两项功耗已完成，独立 FFN 配置的功耗仍待独立测量。')
pbefore(orig[13]._p,'本轮服务器已输出 FF1 与 Encoder 的 TASK_POWER、TASK_ENERGY 及双任务功耗报告完成标记。FF1 的系统平均功耗为 41.2939459 mW、加速器平均功耗为 32.622239 mW；Encoder 单层的系统平均功耗为 41.6877112 mW、加速器平均功耗为 33.240223 mW。表中任务时间由同次输出的系统能耗除以系统平均功耗换算，分别为约 1.449860 ms 与 4.797434 ms。')
pbefore(orig[13]._p,'这些结果为 TT、150 MHz、零延迟门级活动标注条件下的预布局估计，覆盖本轮完整配置的冷任务。完整 FF1 和 Encoder 仿真均已通过输出校验及活动窗口检查后进入功耗报告阶段；活动默认值、传播活动及未知值的细目仍以保存的覆盖报告为准。它们不代表布线后功耗、完整十二层编码器功耗或独立精简 FFN 硬件的功耗。')
pbefore(orig[13]._p,'表中系统能耗按系统平均功耗与完整任务时间相乘得到；加速器功耗为同一活动窗口下的层次分项。两种配置保持独立的数据链路：配置、网表、任务活动和报告必须逐一对应。尚未得到独立综合或有效功耗报告的栏目保留待测，不用局部模块求和或旧版结果代填。')

# New PR chapter goes before the existing script chapter.
anchor=orig[13]._p
h(anchor,'3  PR布局布线细节',1,True)
pbefore(anchor,'本节记录已完成的历史物理实现。固定前端提交为 707cd7f4a0a4d416d11bac71112980079e0a9d34，设计顶层为 e203_cpu_top；该版为 64 MAC，与本轮 16 MAC 的 6bb1bea 分属不同版本。以下版图、执行耗时及导出文件均对应旧版，不据此推断新版的布局面积、布线后时序或功耗。')
h(anchor,'3.1  实现对象与整体流程')
table(anchor,['项目','历史PR实现配置'],[
 ['工具与工艺','ICC2 T-2022.03-SP2-1；SMIC 40 nm；TYP RC'],
 ['时钟目标','6.666667 ns，约 150 MHz；沿用对应版本 SDC'],
 ['加速器配置','8 行矩阵、64 MAC、双向量通路'],
 ['存储宏配置','56 个 RAMSP1024X16；64 个 RAMSP4096X16；合计 120 个宏'],
 ['初始芯核规划','约 45% 利用率；25 μm core offset'],
 ['外框尺寸','约 2599.8 × 2598.56 μm；约 6.756 mm²'],
 ['IO组织','971 个信号端口，划分为 11 个接口组'],
], [2.05,4.85])
pbefore(anchor,'物理实现首先链接标准单元及 SRAM 的 NDM 参考库，载入综合网表与 SDC，再绑定 TYP RC 参数用于互连估计。在统一的设计数据库内完成宏、标准单元、供电、时钟及信号网络的处理，并在各主要阶段保存可重新打开的检查点。流程如下。')
picture(anchor,QA/'pr_flow.png',6.8,'图2  707cd7f版本已执行的基础PR流程')
h(anchor,'3.2  芯核规划与宏布局')
pbefore(anchor,'芯核规划按系统映射规模预留标准单元放置与后续布线空间，初始利用率设为约 45%，核心边界偏移为 25 μm。系统外框约为 2599.8 × 2598.56 μm，属于物理实现使用的芯片几何范围，包含放置空白、存储宏、端口边界和布线资源，与加速器综合映射面积采用不同的统计口径。')
pbefore(anchor,'120 个 SRAM 宏按存储类别组织，宏区域与标准单元区域分别安排。宏布局确定后固定宏实例，并在外围设置 1.12 μm 的 hard keepout，为电源连接、局部互连和标准单元放置保留间隔。后续合法化处理标准单元的站点对齐与重叠关系，防止其侵入宏及保留区域。')
pbefore(anchor,'该安排在保持存储模块分组的同时，为计算和控制逻辑保留连续的内部放置空间。宏位置在时钟和信号布线阶段保持固定，降低跨阶段几何漂移对接口连接和检查点恢复的影响。初始外框仅描述系统版图几何，未用其替代本科面积预算所要求的新增加速器及内部 SRAM 面积。')
h(anchor,'3.3  IO组织与电源网络')
pbefore(anchor,'信号端口按时钟、控制、调试、数据和存储访问接口划分为 11 组；同一总线按位序连续布置，各组之间保留间隔，并在拐角处设置 20 μm 避让。左右边端口使用 M3，上下边端口使用 M4，坐标及层通过脚本明确设置，使版图边界与接口定义保持可对应关系。分组 IO 在后续物理阶段继续保留。')
pbefore(anchor,'电源网络采用环、网格、标准单元电源轨和宏局部连接的层次结构。M7 与 TM2 形成电源环，M2/M6/M7 网格 pitch 为 84 μm，TM2 网格 pitch 为 168 μm；M1 rails 连接标准单元，宏电源引脚通过 M5 局部连接策略接入上层网络。宏周围的低层避让为宏引脚及信号线保留资源。')
table(anchor,['对象','采用的物理组织'],[
 ['信号IO','11 个接口组；组内连续位序；M3/M4 分边放置'],
 ['电源环','M7 水平、TM2 垂直；VDD/VSS 成对组织'],
 ['全局网格','M2/M6/M7：84 μm；TM2：168 μm'],
 ['标准单元电源','M1 rails 与上层网格连接'],
 ['SRAM宏电源','M4 宏引脚经 M5 局部长引脚连接策略接入网格'],
], [2.05,4.85])
pbefore(anchor,'电源图形生成后分别输出连接检查和几何检查报告。网络在逻辑上绑定到 VDD/VSS 与物理上形成连续供电通路属于不同检查对象，最终结论以对应原生报告为准。信号布线完成这一事实与电源网络是否满足签核条件也分别记录，不相互替代。')
h(anchor,'3.4  时钟树与信号布线')
pbefore(anchor,'时钟实现拆分为构树和时钟布线两个独立阶段。build_clock 阶段建立时钟分发结构；route_clock 阶段完成时钟网络布线，并设置传播时钟，用已实现时钟网络参与后续时序分析。两个阶段分别保存设计库与 DEF，便于从明确的时钟实现状态继续后续信号布线。')
pbefore(anchor,'信号网络由 route_auto 执行全局及详细布线；安装版本支持时将详细布线迭代次数设为 3。完成后保存已布线设计，输出 setup、hold、QoR、约束、路由及合法性报告，再导出网表和版图交换文件。此基础实现未执行完整 place_opt、CTS final_opto 或独立 route_opt，因此其定位是已实际跑通的物理实现工程，不作为最终制造签核结果。')
caption(anchor,'表4  历史PR原生阶段执行记录')
table(anchor,['阶段','耗时 / s','原生退出码','已保存产物'],[
 ['时钟树构建','2745','0','阶段设计库与 DEF'],['时钟网络布线','177','0','阶段设计库与 DEF'],
 ['信号网络布线','810','0','已布线设计库与 DEF'],['最终导出','217','0','网表、SDC、DEF、GDSII'],
 ['PG连接检查','44','0','原生连接报告'],['PG几何检查','115','0','原生几何检查报告'],
], [2.1,1,1.1,2.7])
pbefore(anchor,'上述六段合计 4108 s，约 68 分 28 秒，仅表示该轮接续阶段的累计执行时间，不包含先前综合、任务仿真、初始布局或文件复制。退出码为 0 表示对应命令正常执行；质量是否满足要求仍由保存的时序、连接与几何报告分别判定。')
h(anchor,'3.5  版图展示与实现结果')
pbefore(anchor,'图3展示该版本系统的宏布局、内部放置区域及边界端口组织，图4展示最终信号布线与标准单元连接的局部视图。图片均来自既有 707cd7f 工程，仅用于说明历史物理实现成果。')
picture(anchor,assets/'layout_full_public.png',4.4,'图3  707cd7f系统宏布局与分组IO全景')
picture(anchor,assets/'route_detail.png',6.7,'图4  707cd7f最终信号布线与标准单元连接局部')
caption(anchor,'表5  历史PR结果与适用范围')
table(anchor,['检查或交付项','已取得的结果'],[
 ['基础物理实现','宏与IO规划、PG、构树、时钟布线、信号布线及导出已执行'],
 ['最终PG几何检查','777 项：M1 spacing 1 项，M4 spacing 776 项；PG shorts 为 0'],
 ['最终PG连通检查','存在未闭合供电连接；不宣称PG签核通过'],
 ['原生设计交付','nlib、参考 NDM、DEF、Verilog 网表与 SDC'],
 ['GDSII交付','routed_unmerged.gds，约 339 MB；为 unmerged stream'],
 ['持久化验证','PR归档约 1.2 GB；持久盘解包并绑定参考库后已重开最终版图'],
 ['结论边界','已形成可检查、可重开的已布线版图；不等同物理签核完成'],
], [2.1,4.8])
pbefore(anchor,'nlib 保存原生设计对象和连接关系，DEF 记录组件位置及布线，网表和 SDC 记录对应逻辑与约束；GDSII 提供版图几何交换格式。几种文件共同保存可使后续查看同时具有几何与逻辑依据。此次 GDS 为 unmerged，若导入其他版图工具，还需要相应层映射及标准单元、SRAM 的参考版图，不能将单个 stream 文件等同完整制造数据。')

# Renumber existing sections without changing their substantive wording.
for p in orig:
    if p.style.name.startswith('Heading'):
        if p.text.startswith('3  '):p.text=p.text.replace('3  ','4  ',1)
        elif p.text.startswith('3.'):p.text='4.'+p.text[2:]
        elif p.text.startswith('4  '):p.text=p.text.replace('4  ','5  ',1)
        elif p.text.startswith('4.'):p.text='5.'+p.text[2:]
anchor=orig[20]._p
h(anchor,'4.3  历史PR关键命令')
pbefore(anchor,'以下摘录 707cd7f 实际基础 PR 脚本使用的核心命令。库、场景、参考库及文件路径由运行配置绑定；电源网络策略在时钟树构建前执行，阶段结束均保存原生库与 DEF。')
pbefore(anchor,'''# FastEngineeringPr.tcl 核心阶段摘录
open_lib $DesignLib
set_ref_libs -ref_libs $RefLibs
open_block e203_cpu_top
link_block
set_host_options -max_cores 4
set_ignored_layers -min_routing_layer M2 -max_routing_layer TM2
create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros
legalize_placement
# 电源环、网格、M1 rails、M5宏连接由PG策略生成
compile_pg -strategies S_RING707
compile_pg -strategies S_MESH707
clock_opt -from build_clock -to build_clock
save_block
save_lib
clock_opt -from route_clock -to route_clock
set_propagated_clock [all_clocks]
route_auto -max_detail_route_iterations 3
save_block
save_lib
write_def checkpoint.def
write_verilog routed.v
write_sdc routed.sdc
write_gds routed_unmerged.gds''',code=True)
pbefore(anchor,'完整脚本保留安装版本的命令选项检查、分阶段输入输出、执行日志和检查点保存；上述片段用于展示实际实现方法，不替代包含 RC、PG 和场景参数的完整 Tcl 工程。')
anchor=doc._element.body.sectPr
h(anchor,'5.2  历史PR查看与文件定位')
pbefore(anchor,'历史 PR 原运行目录为 /tmp/tpusoc_basic_pr_707cd7f_rwJPkz，持久化归档位于 ~/soc/pr_saved/PR_707cd7f_20261111.tar.gz。已验证的恢复目录为 ~/soc/pr_saved/PR_VIEW；该目录通过 OpenFinalPr.tcl 绑定副本内参考 NDM 并打开最终设计。以下命令仅用于查看既有成果，不会重新启动 PR，也不影响当前功耗进程。')
pbefore(anchor,'''# 服务器另开终端，查看已保存的历史PR版图
cd ~/soc/pr_saved/PR_VIEW
/eda/synopsys/icc2/icc2_2022.03-SP2-1/bin/icc2_shell \\
    -file ./OpenFinalPr.tcl

# 检索归档内的主要文件，不解包或覆盖当前工程
tar -tzf ~/soc/pr_saved/PR_707cd7f_20261111.tar.gz | \\
    egrep 'FastPrSummary|ImplementationReport|07_export|Open.*Pr' ''',code=True)
table(anchor,['历史PR文件','用途'],[
 ['tools/FastEngineeringPr.py\ntools/FastEngineeringPr.tcl','阶段调度及ICC2实际命令；本机源码保存在 Server/Frontend707cd7f/'],
 ['FastPrInputs.json\nFastPrProgress.json','输入配置、各阶段执行记录及最后成功设计库'],
 ['stages/*/ActionResult.json\nstages/*/native.log','原生退出状态、阶段日志与保存状态'],
 ['stages/07_export/','最终 nlib、checkpoint.def、routed.v、routed.sdc、GDS及相关报告'],
 ['FastPrSummary.json\nFastPrChecks.json\nImplementationReport.md','实现结果、检查摘要及完整结果说明'],
 ['OpenFinalPr.tcl 与参考NDM','持久盘恢复及重新打开最终版图'],
], [3.05,3.85])
pbefore(anchor,'当前 6bb1bea 的 DC、SAIF 和功耗文件仍使用前文 $D 与 $P 对应目录。历史 PR 文件和本轮功耗文件分别归档、分别标注版本；复现时先确认当前设计源版本，再选择相应脚本和报告，避免把历史版图的物理检查结果解释为新版实现结果。')

# Formatting only, preserving the user's existing edits and tables.
format_table(tables[2],[3.15,3.75])
for name in ('Title','Heading 1','Heading 2'):
    doc.styles[name].font.color.rgb=RGBColor(0,0,0)
for root in (doc.styles.element,doc.element):
    for el in list(root.iter(qn('w:pBdr'))):el.getparent().remove(el)
for footer in doc.sections[0].footer.paragraphs:
    footer.text='当前综合 6bb1bea  ·  历史PR 707cd7f'
    footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for r in footer.runs:r.font.size=Pt(9)
protected=[original_paragraphs[i] for i in range(len(orig)) if i not in (10,12) and not orig[i].style.name.startswith('Heading')]
final_text=[p.text for p in doc.paragraphs]
assert all(s in final_text for s in protected),'User-edited text lost'
assert [[c.text for c in r.cells] for r in tables[0].rows]==[['面积统计对象','面积 / mm²'],['独立 FFN部分','待独立综合'],['完整加速器部分','0.846539']]
assert hashlib.sha256(SRC.read_bytes()).hexdigest()==original_hash,'User source changed while editing'
doc.save(OUT)
(QA/'EditRecord.json').write_text(json.dumps({'source':str(SRC),'source_sha256':original_hash,'output':str(OUT),'protected_original_paragraphs':len(protected),'method':'edit supplied user document; preserve user prose; timing sentence converted to table; headings renumbered; historic PR added'},ensure_ascii=False,indent=2),encoding='utf-8')
(QA/'PowerEvidence.json').write_text(json.dumps({'source':'user server screenshot 2026-11-13 23:22','source_commit':'6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6','scope':'complete hardware configuration; not independent FFN-only hardware','ff1':{'system_mW':41.293945900000004,'accelerator_mW':32.62223900000001,'system_uJ':59.8704523766209},'encoder':{'system_mW':41.687711199999995,'accelerator_mW':33.240223,'system_uJ':199.994055300564},'duration_method':'system_uJ / system_mW gives milliseconds','summary_server_path':'/tmp/final_power_6bb1bea_11012/PowerSummary.json','status':'COLD_TASK_POWER_REPORTS_COMPLETE_REVIEW_COVERAGE'},indent=2),encoding='utf-8')
print(str(OUT));print('PARAGRAPHS',len(doc.paragraphs),'TABLES',len(doc.tables),'FIGURES',len(doc.inline_shapes))
