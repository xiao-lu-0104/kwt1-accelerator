from pathlib import Path
s=Path('release/e203_plic_diagnostic.vcd').read_text().splitlines(); names={};t=0;events=[]
for line in s:
    p=line.split()
    if p and p[0]=='$var':
        if p[4] in ['clk','rst_n','irq_pend_ena','icb_claim_irq','icb_cmd_valid','icb_cmd_ready','plic_irq_i_r']:names[p[3]]=p[4]
    elif line.startswith('#'):t=int(line[1:])
    elif line.startswith('b'):
        val,code=line[1:].split()
        if code in names:events.append((t,names[code],val))
    elif line and line[0] in '01xz':
        if line[1:] in names:events.append((t,names[line[1:]],line[0]))
for e in events:print(e)
