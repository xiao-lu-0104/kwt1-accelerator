"""Build standalone saved-candidate gate verification; pin prior uploaded scripts."""
import hashlib
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def embedded_manifest(name, expected_sha, marker):
    path = ROOT / 'workspace/Server' / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError('Previously uploaded script changed: ' + name)
    match = re.search("<<'" + marker + "'\n(.*?)" + marker + '\n', path.read_text(), re.S)
    if not match:
        raise ValueError('Missing embedded tools manifest')
    return hashlib.sha256(match[1].encode()).hexdigest()


def main():
    asic_sha = embedded_manifest('tpusoc_shared_asic_20261105_v2.sh',
        '8a9de0f168653b48b2ca41e03d734535e88e5d21200cb95bed34200b54d4cad6', 'TPUSOC_SHARED_ASIC_HASHES')
    report_sha = embedded_manifest('tpusoc_shared_report_20261105_v1.sh',
        'e5bdf6ba0872f8ec0526d9e32adeace53313b824c7bba863c8b54cb638ba8fd7', 'TPUSOC_SHARED_REPORT_HASHES')
    files = [(HERE / name, name) for name in ('Verify.py', 'RecoverReport.py', 'PrepareGate.py', 'AuditCells.tcl')]
    parts, hashes = [], []
    for index, (path, name) in enumerate(files):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        if not data.endswith(b'\n'):
            data += b'\n'
        marker = f'TPUSOC_SHARED_GATE_SOURCE_{index}'
        if marker in data.decode().splitlines():
            raise ValueError('Unsafe heredoc terminator')
        parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
        hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
    parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SHARED_GATE_HASHES\'\n'
                 + ''.join(hashes) + 'TPUSOC_SHARED_GATE_HASHES\n')
    template = (HERE / 'RunGate.sh').read_text()
    if template.count('# __SHARED_GATE_TOOLS__') != 1:
        raise ValueError('Missing unique embedding marker')
    script = template.replace('# __SHARED_GATE_TOOLS__', '\n'.join(parts))
    script = script.replace('__REPORT_TOOLS_SHA__', report_sha).replace('__ASIC_TOOLS_SHA__', asic_sha)
    data = script.replace('\r\n', '\n').encode()
    output = ROOT / 'workspace/Server/tpusoc_shared_gate_20261105_v1.sh'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to change a versioned artifact')
    output.write_bytes(data)
    print('ARTIFACT', output)
    print('BYTES', len(data))
    print('SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
