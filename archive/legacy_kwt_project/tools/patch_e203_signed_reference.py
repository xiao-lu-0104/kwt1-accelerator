#!/usr/bin/env python
"""Fix only E203's simulation reference for signed DIV/REM in an isolated copy.
Keeps all assertions and synthesized datapath unchanged. Python 2.7/3.
"""
from __future__ import print_function
import argparse
import difflib
import hashlib
import io
import json
import os
import re

EXPECTED_LF_SHA256 = 'a981d334e3e1b52b308e73c28a7a27a680cb57aa21a92a919ee3164ba7a59ecb'
MARKER = '     // The special case will need to be handled specially\n'
SIGNED_BLOCK = '''  // Keep signed arithmetic in separate nets: the unsigned special-result
  // branch must not propagate unsigned context into signed DIV/REM.
  wire signed [32:0] golden_signed_dividend = $signed({div_rs1_sign,muldiv_i_rs1});
  wire signed [32:0] golden_signed_divisor = $signed({div_rs2_sign,muldiv_i_rs2});
  wire signed [32:0] golden_signed_safe_divisor =
      (div_by_0 | div_ovf) ? 33'sd1 : golden_signed_divisor;
  wire signed [32:0] golden_signed_quotient = golden_signed_dividend / golden_signed_safe_divisor;
  wire signed [32:0] golden_signed_remainder = golden_signed_dividend % golden_signed_safe_divisor;

'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_bytes(data):
    normalized = data.replace(b'\r\n', b'\n')
    if sha(normalized) != EXPECTED_LF_SHA256:
        raise ValueError('source SHA-256 differs from the verified competition/GitHub reference; refusing to patch')
    text = normalized.decode('utf-8')
    start = text.index('//synopsys translate_off')
    end = text.index('//synopsys translate_on', start)
    prefix, section, suffix = text[:start], text[start:end], text[end:]
    if section.count(MARKER) != 1:
        raise ValueError('expected reference marker is not unique')
    for operation, net in [('div', 'golden_signed_quotient'), ('rem', 'golden_signed_remainder')]:
        pattern = (r'(?m)^  wire \[32:0\] golden_res_' + operation +
                   r'\s*= div_special_cases \? div_special_res :[^\n]*\n[^;\n]+;')
        replacement = ('  wire [32:0] golden_res_' + operation +
                       ' = div_special_cases ? div_special_res :\n     ' + net + ';')
        section, count = re.subn(pattern, replacement, section)
        if count != 1:
            raise ValueError('expected signed %s expression is not unique' % operation)
    section = section.replace(MARKER, SIGNED_BLOCK + MARKER)
    result = (prefix + section + suffix).encode('utf-8')
    if b'\r\n' in data:
        result = result.replace(b'\n', b'\r\n')
    # Strong check: everything outside the original translate_off/on interval is preserved.
    a = data.replace(b'\r\n', b'\n')
    b = result.replace(b'\r\n', b'\n')
    assert a.split(b'//synopsys translate_off', 1)[0] == b.split(b'//synopsys translate_off', 1)[0]
    assert a.split(b'//synopsys translate_on', 1)[1] == b.split(b'//synopsys translate_on', 1)[1]
    assert 'CHECK_GOLD_AND_ACTUAL_SAME:' in section and 'assert property' in section
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--file', required=True)
    p.add_argument('--record', required=True)
    args = p.parse_args()
    with open(args.file, 'rb') as stream:
        original = stream.read()
    updated = patch_bytes(original)
    for path in (args.record, args.record + '.diff'):
        if os.path.exists(path):
            raise ValueError('record already exists; use a fresh isolated run')
    delta = '\n'.join(difflib.unified_diff(
        original.decode('utf-8').splitlines(), updated.decode('utf-8').splitlines(),
        fromfile='original_reference', tofile='signed_reference_fix', lineterm='')) + '\n'
    record = {'source': os.path.abspath(args.file), 'before_sha256': sha(original),
              'after_sha256': sha(updated), 'scope': 'simulation-only signed DIV/REM reference',
              'datapath_changed': False, 'assertions_disabled': False}
    with io.open(args.record + '.diff', 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(delta)
    with io.open(args.record, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, indent=2, sort_keys=True) + u'\n')
    with open(args.file, 'wb') as stream:
        stream.write(updated)
    print('REFERENCE_FIX_APPLIED: signed DIV/REM reference only; all assertions retained')
    print('PATCH_RECORD: ' + args.record)


if __name__ == '__main__':
    try:
        main()
    except (IOError, OSError, ValueError) as error:
        print('ERROR: ' + str(error))
        raise SystemExit(2)
