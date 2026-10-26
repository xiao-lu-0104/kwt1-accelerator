eng=[("QKV-q",64,64,99,4),("QKV-k",64,64,99,4),("QKV-v",64,64,99,4),
     ("score",64,100,99,8),("AV",128,64,99,8),("Oproj",64,64,99,4),
     ("FFN1",64,256,99,4),("FFN2",256,64,99,4),
     ("patchproj",64,64,98,4),("head",64,16,1,4)]
tot=0
print("%-11s %6s %6s %6s %8s"%("engine","IN","OUT","TOK","bytes"))
for n,ind,outd,tok,wb in eng:
    a=tok*ind; w=outd*ind*wb//8
    tot+=a+w
    print("%-11s %6d %6d %6d %8d"%(n,ind,outd,tok,a+w))
print("SRAM TOTAL %d B = %.1f KB = %d bit"%(tot,tot/1024,tot*8))
print("  16b x 4096 macro (65536 bit each): %.1f -> %d macros"%(tot*8/65536, -(-tot*8//65536)))
print("  with 75%% packing efficiency: %d macros"%( -(-int(tot*8/0.75)//65536) ))
