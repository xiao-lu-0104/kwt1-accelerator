from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

ROOT = Path('E:/chipdesign')
OUT = ROOT / 'doc/提交/DC综合与功耗评估_6bb1bea_功耗待填.docx'
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = Inches(.7)
sec.left_margin = sec.right_margin = Inches(.8)
for name in ['Normal', 'Title', 'Heading 1', 'Heading 2']:
    st = doc.styles[name]
    st.font.name = 'Times New Roman'
    st.font.color.rgb = RGBColor(0,0,0)
    st.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), '宋体' if name == 'Normal' else '黑体')
    st.font.size = Pt(11)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.line_spacing = 1.15
doc.styles['Title'].font.size = Pt(20)
doc.styles['Heading 1'].font.size = Pt(13)
doc.styles['Heading 1'].paragraph_format.space_before = Pt(10)

def para(s):
    p = doc.add_paragraph(s)
    p.paragraph_format.first_line_indent = Pt(22)
    return p

def table(headers, rows, widths):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for c,w in zip(t.columns,widths): c.width = Inches(w)
    for c,s in zip(t.rows[0].cells,headers): c.text = s
    for row in rows:
        for c,s in zip(t.add_row().cells,row): c.text = s
    for i,row in enumerate(t.rows):
        for j,c in enumerate(row.cells):
            c.width = Inches(widths[j])
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            pr = c._tc.get_or_add_tcPr()
            borders = OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                e=OxmlElement('w:'+edge); e.set(qn('w:val'),'single'); e.set(qn('w:sz'),'4'); e.set(qn('w:color'),'D9D9D9'); borders.append(e)
            pr.append(borders)
            margins=OxmlElement('w:tcMar')
            for edge in ['top','bottom','left','right']:
                e=OxmlElement('w:'+edge); e.set(qn('w:w'),'80'); e.set(qn('w:type'),'dxa'); margins.append(e)
            pr.append(margins)
            if i == 0:
                sh=OxmlElement('w:shd'); sh.set(qn('w:fill'),'E7EDF3'); pr.append(sh)
            for p in c.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for r in p.runs:
                    r.font.size = Pt(10.5)
                    r.bold = i == 0
        np=OxmlElement('w:cantSplit'); row._tr.get_or_add_trPr().append(np)
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    spacer=doc.add_paragraph()
    spacer.paragraph_format.space_after=Pt(3)
    spacer.paragraph_format.line_spacing=Pt(2)
    spacer.add_run().font.size=Pt(2)
    return t

doc.add_paragraph('DC综合与功耗评估', 'Title')
para('本设计采用 SMIC 40 nm RVT 工艺库进行逻辑综合，在 TT、1.1 V、25 ℃条件下，以 150 MHz 为目标频率完成加速器映射及增量保持时间优化。以下给出固定版本 6bb1bea 的综合面积与时序结果，功耗结果预留待填。')
doc.add_paragraph('1  DC综合结果', 'Heading 1')
para('综合顶层为 SubmissionAccelerator，配置为 16 MAC。统计范围包括 TpuNice、TpuFf1Stream、计算核心、TpuLocalCopy、TpuIcb 及 56 个私有 SRAM 宏。私有存储采用 RAMSP1024X16，总容量为 112 KiB。综合保留模块层次，并使用实际 SRAM 宏库完成映射。')
table(['面积组成', '面积 / μm²', '面积 / mm²'], [
    ['逻辑及接口', '334,221.871', '0.334222'],
    ['私有 SRAM 宏', '512,317.367', '0.512317'],
    ['加速器合计', '846,539.238', '0.846539'],
], [2.7,2.1,2.1])
para('上述面积为综合映射单元面积，包含私有 SRAM 宏；不包含原平台 CPU、共享 SRAM 及新版 CPU/DMA SystemBus 仲裁器。因此，该数值对应本次加速器综合边界，完整新增硬件面积仍须另计仲裁器面积。')
table(['时序指标', '约束或结果'], [
    ['时钟周期', '6.666667 ns（150 MHz）'],
    ['Setup WNS', '+0.197581 ns'],
    ['Hold WNS', '+0.00112969 ns'],
], [3.5,3.4])
para('在所声明的接口时序预算下，加速器边界的建立时间与保持时间检查均满足约束。综合使用 0.200 ns 的 setup 时钟不确定度和 0.100 ns 的 hold 时钟不确定度；以上结论适用于该加速器边界，不代表完整系统的时序收敛结论。')
doc.add_paragraph('2  功耗评估', 'Heading 1')
para('功耗拟采用同版本门级网表与任务活动文件进行分析，分别报告完整系统和加速器统计范围内的平均功耗。任务窗口覆盖输入及参数装载、调度、计算和最终输出写回。以下结果待有效任务仿真及功耗分析完成后填写。')
table(['任务', '系统平均功耗\n/ mW', '加速器平均功耗\n/ mW', '任务时间\n/ ms', '系统单任务能耗\n/ μJ'], [
    ['FF1 冷任务', '待填', '待填', '待填', '待填'],
    ['Encoder 单层冷任务', '待填', '待填', '待填', '待填'],
], [1.55,1.4,1.4,1.1,1.45])
p=doc.add_paragraph('分析条件及功耗分量：待填（工艺角、电压、频率、活动覆盖率、内部功耗、开关功耗与漏电功耗）。')
p.paragraph_format.space_after=Pt(0)
for r in p.runs:r.font.size=Pt(10)
footer=sec.footer.paragraphs[0]
footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=footer.add_run('版本 6bb1bea  ·  2026年11月13日')
r.font.size=Pt(9)
doc.core_properties.title='DC综合与功耗评估'
doc.core_properties.subject='6bb1bea 加速器综合结果及功耗待填'
for root in [doc.styles.element, doc.element]:
    for elem in list(root.iter(qn('w:pBdr'))):
        elem.getparent().remove(elem)
OUT.parent.mkdir(parents=True,exist_ok=True)
doc.save(OUT)
print(OUT)
