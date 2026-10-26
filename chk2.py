D,TOK,TP,FF=64,99,98,256
TACT=TOK*D; PACT=TP*D; NP=TOK*TOK; HACT=TOK*FF
def b(w,n): return w*n
reg={}
reg["kwt_top.act_buf"]=b(8,PACT)
for n in (TACT,):
    for nm in ("pp_buf","cp_buf","out_buf"): reg["kwt_top."+nm]=b(8,n)
reg["kwt_top.hd_buf"]=b(8,D); reg["kwt_top.lg"]=b(8,16)
reg["kwt_encoder_12.xhold"]=b(8,TACT)
reg["enc_layer.x_buf"]=b(8,TACT); reg["enc_layer.o_buf"]=b(8,TACT)
reg["enc_layer.r1_buf"]=b(16,TACT); reg["enc_layer.x1_buf"]=b(8,TACT)
reg["enc_layer.h_buf"]=b(8,HACT); reg["enc_layer.f_buf"]=b(8,TACT)
reg["enc_layer.r2_buf"]=b(16,TACT)
reg["enc_layer.ln_g/b"]=b(16,128)
reg["attention.x_buf"]=b(8,TACT); reg["attention.q_buf"]=b(8,TACT)
reg["attention.k_buf"]=b(8,TACT+4); reg["attention.v_buf"]=b(8,TACT+196)
reg["attention.score_buf"]=b(16,TOK*100); reg["attention.p_buf"]=b(8,NP+4)
reg["attention.ctx_buf"]=b(8,TACT)
reg["layernorm.x_buf"]=b(16,TOK*D); reg["layernorm.gamma/beta"]=b(16,128)
reg["softmax(x4)"]=b(16,TOK)*2*4
print("--- reg arrays ---")
tot=0
for k,v in reg.items():
    tot+=v; print("%-26s %8d bit %6.1f KB"%(k,v,v/8192))
print("REG TOTAL %d bit = %.1f KB = %d FFs"%(tot,tot/8192,tot))
