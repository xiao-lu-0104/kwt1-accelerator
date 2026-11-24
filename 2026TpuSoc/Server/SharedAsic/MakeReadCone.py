"""Package one read-only first-X and Word-cone evidence reader."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
source = (HERE / 'ReadCone.py').read_text().replace('\r\n', '\n')
marker = 'TPUSOC_READ_CONE_PYTHON'
if marker in source.splitlines():
    raise ValueError('Unsafe heredoc terminator')
script = ('#!/usr/bin/env bash\nset -euo pipefail\n'
          'py=$(command -v python3 || true)\n'
          '[[ -n "$py" ]] || { echo "ERROR: Python 3 required"; exit 2; }\n'
          '"$py" - "$@" <<\'' + marker + "'\n" + source + '\n' + marker + '\n').encode()
out = ROOT / 'workspace/Server/tpusoc_read_cone_20261105_v1.sh'
if out.exists() and out.read_bytes() != script:
    raise ValueError('Refusing to replace a versioned artifact')
out.write_bytes(script)
print('ARTIFACT', out)
print('BYTES', len(script))
print('SHA256', hashlib.sha256(script).hexdigest())
