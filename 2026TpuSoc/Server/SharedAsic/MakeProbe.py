"""Package immutable baseline/candidate and passive mirror probes."""
import hashlib
from pathlib import Path
from MakeGate import embedded_manifest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    previous_sha = embedded_manifest('tpusoc_shared_gate_20261105_v1.sh',
        'c556cb1188f1579c4d6991155450a7aead0a03d52fadc7eb68b587e1d4bf2c51', 'TPUSOC_SHARED_GATE_HASHES')
    files = [(HERE / name, name) for name in ('Verify.py', 'RecoverReport.py', 'PrepareGate.py',
              'PrepareProbe.py', 'IcbMirror.sv', 'GateWatch.sv')]
    parts, hashes = [], []
    for index, (path, name) in enumerate(files):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        if not data.endswith(b'\n'):
            data += b'\n'
        marker = f'TPUSOC_GATE_PROBE_SOURCE_{index}'
        if marker in data.decode().splitlines():
            raise ValueError('Unsafe heredoc terminator')
        parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
        hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
    parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_GATE_PROBE_HASHES\'\n'
                 + ''.join(hashes) + 'TPUSOC_GATE_PROBE_HASHES\n')
    template = (HERE / 'RunProbe.sh').read_text()
    if template.count('# __GATE_PROBE_TOOLS__') != 1:
        raise ValueError('Missing unique embedding marker')
    text = template.replace('# __GATE_PROBE_TOOLS__', '\n'.join(parts))
    data = text.replace('__GATE_V1_TOOLS_SHA__', previous_sha).replace('\r\n', '\n').encode()
    out = ROOT / 'workspace/Server/tpusoc_gate_probe_20261105_v1.sh'
    if out.exists() and out.read_bytes() != data:
        raise ValueError('Refusing to change a versioned artifact')
    out.write_bytes(data)
    print('ARTIFACT', out)
    print('BYTES', len(data))
    print('SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
