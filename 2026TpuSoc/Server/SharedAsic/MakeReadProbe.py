"""Create one Python-only server inspection script; no EDA invocation."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
data = (HERE / 'ReadProbe.py').read_bytes().replace(b'\r\n', b'\n')
text = data.decode()
marker = 'TPUSOC_READ_PROBE_PYTHON'
if marker in text.splitlines():
    raise ValueError('Unsafe heredoc terminator')
script = ('#!/usr/bin/env bash\nset -euo pipefail\n'
          'py=$(command -v python3 || true)\n'
          '[[ -n "$py" ]] || { echo "ERROR: Python 3 required"; exit 2; }\n'
          '"$py" - "$@" <<\'' + marker + "'\n" + text + '\n' + marker + '\n').encode()
out = ROOT / 'workspace/Server/tpusoc_read_probe_20261105_v1.sh'
if out.exists() and out.read_bytes() != script:
    raise ValueError('Refusing to change a versioned artifact')
out.write_bytes(script)
print('ARTIFACT', out)
print('BYTES', len(script))
print('SHA256', hashlib.sha256(script).hexdigest())
