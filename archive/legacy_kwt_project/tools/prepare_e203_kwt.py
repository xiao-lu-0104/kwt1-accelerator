#!/usr/bin/env python
"""Replace one example slave in an isolated E203 RTL snapshot (Python 2/3)."""
from __future__ import print_function
import argparse
import hashlib
import io
import json
import os
import re

EXPECTED_MEMS = 'dc63cbcc9ebe9331c824c27f6f3645f0f330740573ee1b9a52dc5ca259a339fd'


def read(path):
    with io.open(path, 'r', encoding='utf-8') as stream:
        return stream.read().replace('\r\n', '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', required=True, help='New isolated copy, never original platform')
    parser.add_argument('--record', required=True)
    args = parser.parse_args()
    root = os.path.abspath(args.rtl)
    # The runner creates this marker only inside its new snapshot.
    if not os.path.isfile(os.path.join(root, '.kwt_isolated_snapshot')):
        raise ValueError('Missing isolated-snapshot marker; refusing to edit this directory')
    config = read(os.path.join(root, 'core', 'config.v'))
    active = re.sub(r'/\*.*?\*/|//[^\n]*', '', config, flags=re.S)
    for name, value in [('ITCM_ADDR_WIDTH', '18'), ('DTCM_ADDR_WIDTH', '18')]:
        found = re.findall(r'^\s*`define\s+E203_CFG_'+name+r'\s+(\d+)\s*$', active, re.M)
        if found != [value]:
            raise ValueError('Expected existing E203_CFG_%s=%s; got %s (capacity will not be changed)' % (name, value, found))
    if not re.search(r'^\s*`define\s+E203_CFG_SUPPORT_MCYCLE_MINSTRET\s*$', active, re.M):
        raise ValueError('Platform mcycle support is not enabled')
    for name, address in [('ITCM_ADDR_BASE', '80000000'), ('DTCM_ADDR_BASE', '90000000')]:
        match = re.findall(r'^\s*`define\s+E203_CFG_'+name+r"\s+`E203_CFG_ADDR_SIZE'h([0-9a-fA-F_]+)\s*$", active, re.M)
        if len(match) != 1 or match[0].replace('_', '').lower() != address:
            raise ValueError('Unexpected platform TCM base '+name)
    path = os.path.join(root, 'subsys', 'e203_subsys_mems.v')
    original = read(path)
    before = hashlib.sha256(original.encode('utf-8')).hexdigest()
    if before != EXPECTED_MEMS:
        raise ValueError('Platform peripheral source differs from the checked baseline: '+before)
    pattern = (r'sirv_expl_axi_slv\s*#\s*\(\s*\.AW\s*\(32\),\s*'
               r'\.DW\s*\(`E203_XLEN\)\s*\)\s*u_perips_expl_axi_slv\s*\(')
    updated, count = re.subn(pattern, 'kwt_encoder_axi_top u_perips_expl_axi_slv (', original)
    if count != 1:
        raise ValueError('Expected exactly one known example peripheral instance')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(updated)
    record = dict(file='subsys/e203_subsys_mems.v', before_lf_sha256=before,
                  after_lf_sha256=hashlib.sha256(updated.encode('utf-8')).hexdigest(),
                  change='one example AXI slave replaced; all port mappings retained',
                  cpu_datapath='unchanged', tcm_capacity='existing 256 KiB each; unchanged')
    with io.open(args.record, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, indent=2, ensure_ascii=True)+u'\n')
    print('PLATFORM_PREPARED: one AXI peripheral replaced; CPU and TCM configuration unchanged')


if __name__ == '__main__':
    main()
