from pypdf import PdfReader
r = PdfReader("doc/2026NICT EDA平台_用户登录及使用手册_V10.pdf")
print("pages:", len(r.pages))
out=[]
for i,p in enumerate(r.pages):
    t=p.extract_text() or ""
    out.append(f"\n===== PAGE {i+1} =====\n{t}")
txt="".join(out)
open("doc/EDA平台手册_文本.txt","w",encoding="utf-8").write(txt)
print("chars:", len(txt))
