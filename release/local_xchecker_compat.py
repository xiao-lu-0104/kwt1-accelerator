from pathlib import Path
p=Path('release/e203_kwt_local/platform/general/sirv_gnrl_xchecker.v')
s=p.read_text()
start=s.index('CHECK_THE_X_VALUE:')
end=s.index('\nendmodule',start)
old=s[start:end]
new='''// LOCAL XSIM diagnostic compatibility: keep the same X predicate and clock.
// The original concurrent assertion stays unchanged in the VCS server package.
always @(posedge clk) begin
  if ((^i_dat) === 1'bx) $fatal(1,"Local event X checker: unknown enable");
end
'''
p.with_suffix('.v.original').write_text(s,encoding='utf-8',newline='\n')
p.write_text(s[:start]+new+s[end:],encoding='utf-8',newline='\n')
Path('release/e203_xchecker_compatibility.txt').write_text('LOCAL XSIM diagnostic only. PLIC X assertion fired at 223344 ps while VCD and edge trace showed i_dat=0, rst_n=0. Original VCS source/checks remain untouched. Same-predicate immediate check used only in this local copy.\n',encoding='utf-8')
