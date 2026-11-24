"""Validate the exact server evidence reviewed on 2026-11-02, Python 2.7/3."""
from __future__ import print_function
import hashlib
import json
import os
import sys

ROOT = sys.argv[1]
OUT = sys.argv[2]
EXPECTED = {
    'verilog/RAMSP1024X16.v': '81b55d87d5e6821d44037d6f0290ec89c9edb9582eb1932957f181aefc300d51',
    'lib/RAMSP1024X16_tt_1p10v_1p10v_25c.lib': '7cf092257dfe18f32affee2d1a071b198b7cc68cb50b5bc71b0fdc98a79cfdb1',
}
for relative, expected in sorted(EXPECTED.items()):
    path = os.path.join(ROOT, 'RAMSP1024X16', *relative.split('/'))
    with open(path, 'rb') as stream:
        actual = hashlib.sha256(stream.read()).hexdigest()
    if actual != expected:
        raise ValueError('Reviewed vendor input changed: %s; actual=%s expected=%s' %
                         (relative, actual, expected))
    print('VERIFIED_INPUT: ' + relative + ' ' + actual)
report = dict(macro='RAMSP1024X16', inputs_sha256=EXPECTED,
              reviewed_ports='Q CLK CEN WEN A D EMA EMAW GWEN RET1N',
              power_pin_mode='default logical interface; no POWER_PINS define',
              controls=dict(CEN='~en', GWEN='~write', WEN='16h0000',
                            EMA=2, EMAW=0, RET1N=1),
              topology='56x1024x16, 112KiB, one common rising-edge clock',
              expected_library_area_per_macro=9148.524700,
              vendor_simulation='PENDING', asic_synthesis='PENDING')
with open(OUT, 'w') as stream:
    json.dump(report, stream, indent=2, sort_keys=True)
    stream.write('\n')
print('REVIEWED_INPUTS_VERIFIED')
