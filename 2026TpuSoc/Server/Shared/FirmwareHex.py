"""Generate a full little-endian 256 KiB ITCM initialization image."""
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
if len(data) > 262144:
    raise ValueError('Firmware exceeds ITCM capacity')
data += bytes(262144 - len(data))
Path(sys.argv[2]).write_text(''.join(f'{int.from_bytes(data[i:i+8], "little"):016x}\n'
                                    for i in range(0, len(data), 8)))
