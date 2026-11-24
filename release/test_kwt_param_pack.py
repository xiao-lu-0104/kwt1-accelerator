from pathlib import Path
import importlib.util,struct
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('packer',root/'tools/pack_kwt_param_stream.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
directory=root/'sim/vectors/enc12'
records=module.pack_records(directory)
assert len(records)==45384
def values(name): return [int(x,16) for x in (directory/name).read_text().split()]
for layer in range(12):
    block=records[layer*3782:(layer+1)*3782]
    assert [((word>>(4*i))&15) for word in block[:3072] for i in range(16)]==values('wrom.mem')[layer*49152:(layer+1)*49152]
    coefficients=block[3072:3648]
    assert [word&0xffffffff for word in coefficients]==values('brom_b.mem')[layer*576:(layer+1)*576]
    assert [word>>32 for word in coefficients]==values('brom_m.mem')[layer*576:(layer+1)*576]
    assert [word&0xffff for word in block[3648:3776]]==values('lnrom_g.mem')[layer*128:(layer+1)*128]
    assert [(word>>16)&0xffff for word in block[3648:3776]]==values('lnrom_b.mem')[layer*128:(layer+1)*128]
    assert [word>>32 for word in block[3776:]]==values('lconst.mem')[layer*6:(layer+1)*6]
payload=b''.join(struct.pack('<Q',record) for record in records)
assert len(payload)==363072
assert struct.unpack('<II',payload[:8])==(records[0]&0xffffffff,records[0]>>32)
print('PASS: all twelve layers round-trip every weight, coefficient, LN value and constant; little-endian 32-bit words')
