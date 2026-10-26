import re, glob, os
tot=0
rows=[]
for f in glob.glob('rtl/*.v'):
    s=open(f,encoding='utf-8',errors='ignore').read()
    # reg arrays: reg [w-1:0] name [0:d]
    for m in re.finditer(r'reg\s*(?:signed\s*)?\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*(\w+)\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]', s):
        hi,lo,name,d0,d1=int(m.group(1)),int(m.group(2)),m.group(3),int(m.group(4)),int(m.group(5))
        w=abs(hi-lo)+1; n=abs(d1-d0)+1
        rows.append((os.path.basename(f),name,w,n,w*n))
    for m in re.finditer(r'reg\s+(\w+)\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]', s):
        name=m.group(1); a=abs(int(m.group(2))-int(m.group(3)))+1; b=abs(int(m.group(4))-int(m.group(5)))+1
        rows.append((os.path.basename(f),name,1,a*b,a*b))
agg={}
for f,n,w,d,bit in rows:
    agg[(f,n)]=(w,d,bit)
print("bit  (KB)  file / array")
for (f,n),(w,d,bit) in sorted(agg.items(), key=lambda x:-x[1][2]):
    tot+=bit
    print("%8d %7.1f  %-24s %-12s w=%d d=%d" % (bit, bit/8192, f, n, w, d))
print("TOTAL reg arrays = %d bit = %.1f KB = %d FFs" % (tot, tot/8192, tot))
