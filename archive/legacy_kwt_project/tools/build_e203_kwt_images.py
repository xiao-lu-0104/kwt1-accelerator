"""Build an RV32 bare-metal C application and two 256-KiB TCM test images."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
from pack_kwt_param_stream import pack_records

ROOT = Path(__file__).resolve().parents[1]


def layout():
    raw = json.loads((ROOT/'sw/e203/layout.json').read_text(encoding='utf-8'))
    return {k: int(v, 0) if isinstance(v, str) else v for k, v in raw.items()}


def generate_config(out, cfg):
    constants = {
        'KWT_PARAM_A': cfg['itcm_base']+cfg['param_a_offset'],
        'KWT_PARAM_B': cfg['dtcm_base']+cfg['param_b_offset'],
        'KWT_SPLIT_LAYERS': cfg['split_layers'],
        'KWT_INPUT_BUFFER': cfg['dtcm_base']+cfg['input_offset'],
        'KWT_OUTPUT_BUFFER': cfg['dtcm_base']+cfg['output_offset'],
        'KWT_SCRATCH': cfg['dtcm_base']+cfg['scratch_offset'],
        'KWT_MAILBOX': cfg['dtcm_base']+cfg['mailbox_offset'],
    }
    (out/'kwt_e203_layout.h').write_text(
        '#ifndef KWT_E203_LAYOUT_H\n#define KWT_E203_LAYOUT_H\n'+
        ''.join('#define %s 0x%x\n' % item for item in constants.items())+
        '#endif\n', encoding='ascii', newline='\n')
    (out/'kwt_e203_images.vh').write_text(
        ''.join("`define %s 32'h%08x\n" % item for item in constants.items())+
        "`define KWT_TCM_BYTES %d\n" % cfg['tcm_bytes'],
        encoding='ascii', newline='\n')
    (out/'kwt_e203.ld').write_text('''OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
  ROM (rx) : ORIGIN = 0x%x, LENGTH = 0x%x
  RAM (rw) : ORIGIN = 0x%x, LENGTH = 0x%x
}
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) *(.srodata*) } >ROM :text
  .data : { *(.data*) *(.sdata*) } >RAM :data
  .bss (NOLOAD) : { . = ALIGN(4); __bss_start = .; *(.bss*) *(.sbss*) *(COMMON)
                   . = ALIGN(4); __bss_end = .; } >RAM :data
  __stack_top = 0x%x;
  /DISCARD/ : { *(.eh_frame*) *(.comment*) }
}
''' % (cfg['itcm_base'], cfg['text_bytes'], cfg['dtcm_base']+cfg['data_offset'],
       cfg['data_bytes'], cfg['dtcm_base']+cfg['stack_top_offset']),
        encoding='ascii', newline='\n')


def load_elf(path, memories, cfg):
    data = path.read_bytes()
    if data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    header = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    _, machine, _, entry, phoff, _, _, _, phsize, phnum, _, _, _ = header
    if machine != 243 or entry != cfg['itcm_base'] or phsize != 32:
        raise ValueError('Unexpected ELF machine/entry/program header size')
    segments = []
    for i in range(phnum):
        kind, offset, address, physical, size, memsize, flags, _ = struct.unpack_from('<8I', data, phoff+i*phsize)
        if kind != 1 or memsize == 0:
            continue
        if size > memsize or offset+size > len(data) or physical != address:
            raise ValueError('Invalid ELF load segment')
        region = None
        for name, base, start, length in (
            ('itcm', cfg['itcm_base'], 0, cfg['text_bytes']),
            ('dtcm', cfg['dtcm_base'], cfg['data_offset'], cfg['data_bytes']),
        ):
            if base+start <= address and address+memsize <= base+start+length:
                memories[name][address-base:address-base+size] = data[offset:offset+size]
                region = name
                break
        if region is None:
            raise ValueError('ELF segment overlaps reserved model/data buffers: %#x' % address)
        if any(address < old['address']+old['memsize'] and old['address'] < address+memsize for old in segments):
            raise ValueError('Overlapping ELF load segments')
        segments.append(dict(region=region, address=address, filesz=size, memsize=memsize, flags=flags))
    if not any(s['region'] == 'itcm' and s['flags'] & 1 for s in segments):
        raise ValueError('No executable ITCM segment')
    return segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    compiler = parser.add_mutually_exclusive_group(required=True)
    compiler.add_argument('--zig', type=Path, help='Zig executable; its clang/lld cross-compile to RV32')
    compiler.add_argument('--cc', help='RISC-V GCC executable')
    compiler.add_argument('--from-elf', type=Path, help='Regenerate images from an existing checked program ELF')
    parser.add_argument('--march', default='rv32imac_zicsr_zifencei', help='GCC ISA string')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--vectors', type=Path, default=ROOT/'sim/vectors/enc12')
    parser.add_argument('--smoke', action='store_true', help='Build a short CPU/MMIO path check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cfg = layout()
    generate_config(out, cfg)
    common = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-ffreestanding',
              '-fno-builtin', '-fno-stack-protector', '-fno-pic', '-msmall-data-limit=0', '-mno-relax',
              '-nostdlib', '-I', str(ROOT/'sw'), '-I', str(out),
              '-Wl,-T,'+str(out/'kwt_e203.ld'),
              str(ROOT/'sw/e203/start.S'),
              str(ROOT/'sw/e203/kwt_app.c'), str(ROOT/'sw/kwt_encoder.c'),
              '-o', str(out/'program.elf')]
    if args.smoke:
        common.insert(0, '-DKWT_CPU_SMOKE')
    command = None
    if args.zig:
        command = [str(args.zig.resolve()), 'cc', '-target', 'riscv32-freestanding',
                   '-mcpu=generic_rv32+m+a+c+zicsr+zifencei'] + common
    elif args.cc:
        command = [args.cc, '-march='+args.march, '-mabi=ilp32', '-mcmodel=medany'] + common
    if command:
        subprocess.run(command, check=True)
    else:
        (out/'program.elf').write_bytes(args.from_elf.read_bytes())
    memories = {name: bytearray(cfg['tcm_bytes']) for name in ('itcm', 'dtcm')}
    segments = load_elf(out/'program.elf', memories, cfg)
    payload = b''.join(struct.pack('<Q', x) for x in pack_records(args.vectors))
    split = cfg['split_layers']*30256
    if len(payload) != 363072 or split != 181536:
        raise ValueError('Unexpected parameter layout')
    regions = {
        'itcm': [(0, cfg['text_bytes']), (cfg['param_a_offset'], split)],
        'dtcm': [(cfg['param_b_offset'], len(payload)-split), (cfg['input_offset'], 6336),
                 (cfg['output_offset'], 6336), (cfg['scratch_offset'], 30256),
                 (cfg['data_offset'], cfg['data_bytes']),
                 (cfg['stack_bottom_offset'], cfg['stack_top_offset']-cfg['stack_bottom_offset']),
                 (cfg['mailbox_offset'], 256)],
    }
    for ranges in regions.values():
        ranges.sort()
        for i, (start, size) in enumerate(ranges):
            if start < 0 or size <= 0 or start+size > cfg['tcm_bytes'] or (i and ranges[i-1][0]+ranges[i-1][1] > start):
                raise ValueError('TCM memory regions overlap or exceed capacity')
    a, b = cfg['param_a_offset'], cfg['param_b_offset']
    memories['itcm'][a:a+split] = payload[:split]
    memories['dtcm'][b:b+len(payload)-split] = payload[split:]
    inputs = bytes(int(x, 16) for x in (args.vectors/'x.mem').read_text().split())
    if len(inputs) != 6336:
        raise ValueError('Wrong input byte count')
    a = cfg['input_offset']
    memories['dtcm'][a:a+len(inputs)] = inputs
    for name, memory in memories.items():
        (out/(name+'.mem')).write_text(''.join('%02x\n' % x for x in memory), encoding='ascii', newline='\n')
    sources = [ROOT/'sw/kwt_encoder.c', ROOT/'sw/kwt_encoder.h', *sorted((ROOT/'sw/e203').glob('*'))]
    record = dict(command=command, smoke=args.smoke, source_sha256={str(p.relative_to(ROOT)).replace('\\', '/'):
                  hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sources},
                  layout=cfg, segments=segments, parameter_sha256=hashlib.sha256(payload).hexdigest(),
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    (out/'build.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('CPU_IMAGES_COMPLETE: RV32 C driver; 2 x 256 KiB TCM; full 12-layer model/input')
    print('CPU_PROGRAM_SHA256: '+record['files']['program.elf'])
    print('OUTPUT_DIR: '+str(out))


if __name__ == '__main__':
    main()
