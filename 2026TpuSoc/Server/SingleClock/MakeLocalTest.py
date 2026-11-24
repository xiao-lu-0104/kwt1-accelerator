"""Adapt only the old simulator host to the new upstream single-clock top."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'Sim/SocTest.cpp'
text = source.read_text()
changes = [
    ('VE203Tpu', 'VE203TpuBackend'),
    ('DdrModel DdrBus{100};', 'DdrModel DdrBus{150};'),
    ('const bool CpuRising = TimeStep % 20 == 10;', 'const bool CpuRising = TimeStep % 6 == 3;'),
    ('            Top.CpuClock = TimeStep % 20 >= 10;\n', ''),
    ('Clock profile: TPU 100 MHz, CPU 30 MHz', 'Clock profile: CPU+TPU shared 150 MHz'),
    ('// One microstep = 5/3 ns: TPU half-period=3, CPU half-period=10.\n        // Ten TPU cycles and three CPU cycles therefore take exactly 100 ns.',
     '// Six logical microsteps per shared CPU+TPU cycle.\n        // DDR bandwidth/latency model is explicitly parameterized at 150 MHz.'),
]
for old, new in changes:
    if old not in text:
        raise ValueError('Host adaptation anchor absent: '+old)
    text = text.replace(old, new)
out = ROOT / 'workspace/Checks/SingleClock20261102'
out.mkdir(parents=True, exist_ok=True)
(out / 'SocTest.cpp').write_text(text)
print('HOST_SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest())
print('HOST_ADAPTATION: original firmware/scoreboard, shared-edge sampling, DDR=150MHz; RTL unchanged')
