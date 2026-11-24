"""Build immutable read-only recovery for the exact uploaded synthesis v2."""
import hashlib
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    previous = ROOT / 'workspace/Server/tpusoc_shared_asic_20261105_v2.sh'
    if hashlib.sha256(previous.read_bytes()).hexdigest() != '8a9de0f168653b48b2ca41e03d734535e88e5d21200cb95bed34200b54d4cad6':
        raise ValueError('Expected uploaded synthesis v2 script')
    match = re.search(r"<<'TPUSOC_SHARED_ASIC_HASHES'\n(.*?)TPUSOC_SHARED_ASIC_HASHES\n", previous.read_text(), re.S)
    if not match:
        raise ValueError('Missing original tools manifest')
    previous_sha = hashlib.sha256(match[1].encode()).hexdigest()
    files = [(HERE / name, name) for name in ('Verify.py', 'RecoverReport.py', 'Snapshot.tcl')]
    files += [(ROOT / 'Server/Backend/AsicCommon.tcl', 'AsicCommon.tcl'),
              (ROOT / 'Server/SingleClock/HoldPolicy.tcl', 'HoldPolicy.tcl')]
    parts, hashes = [], []
    for index, (path, name) in enumerate(files):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        if not data.endswith(b'\n'):
            data += b'\n'
        marker = f'TPUSOC_SHARED_REPORT_SOURCE_{index}'
        if marker in data.decode().splitlines():
            raise ValueError('Unsafe heredoc terminator')
        parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
        hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
    parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SHARED_REPORT_HASHES\'\n'
                 + ''.join(hashes) + 'TPUSOC_SHARED_REPORT_HASHES\n')
    template = (HERE / 'RunReport.sh').read_text()
    if template.count('# __SHARED_REPORT_TOOLS__') != 1:
        raise ValueError('Missing unique embedding marker')
    script = template.replace('# __SHARED_REPORT_TOOLS__', '\n'.join(parts))
    data = script.replace('__PREVIOUS_TOOLS_SHA__', previous_sha).replace('\r\n', '\n').encode()
    output = ROOT / 'workspace/Server/tpusoc_shared_report_20261105_v1.sh'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to change an existing versioned artifact')
    output.write_bytes(data)
    print('ARTIFACT', output)
    print('BYTES', len(data))
    print('SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
