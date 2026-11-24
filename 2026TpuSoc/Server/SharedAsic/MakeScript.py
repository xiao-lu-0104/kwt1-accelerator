"""Embed reviewed tools, pin the functional bundle, and produce one uploadable script."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    bundle = ROOT / 'workspace/Server/tpusoc_shared_20261105_v1'
    manifest = bundle / 'MANIFEST.sha256'
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if manifest_sha != 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83':
        raise ValueError('Unexpected reviewed shared_v1 manifest')
    for line in manifest.read_text().splitlines():
        sha, name = line.split('  ', 1)
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Local functional bundle changed: ' + name)
    for line in manifest.read_text().splitlines():
        sha, name = line.split('  ', 1)
        if name.startswith('Rtl/') or name == 'Backend/e203_subsys_nice_core.sv':
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
                raise ValueError('Current design differs from tested bundle: ' + name)
    files = [(HERE / name, name) for name in ('Verify.py', 'Constraints.tcl', 'Run.tcl')]
    files += [(ROOT / 'Server/Backend' / name, name)
              for name in ('AsicCommon.tcl', 'CompileSpLib.tcl', 'VerifyMacro.py')]
    files += [(ROOT / 'Server/SingleClock/HoldPolicy.tcl', 'HoldPolicy.tcl')]
    parts, hashes = [], []
    for index, (path, name) in enumerate(files):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        if not data.endswith(b'\n'):
            data += b'\n'
        marker = f'TPUSOC_SHARED_ASIC_SOURCE_{index}'
        text = data.decode()
        if marker in text.splitlines():
            raise ValueError('Unsafe heredoc terminator')
        parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{text}{marker}\n')
        hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
    parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SHARED_ASIC_HASHES\'\n'
                 + ''.join(hashes) + 'TPUSOC_SHARED_ASIC_HASHES\n')
    template = (HERE / 'Run.sh').read_text()
    if template.count('# __SHARED_ASIC_TOOLS__') != 1:
        raise ValueError('Missing unique embedding marker')
    script = template.replace('# __SHARED_ASIC_TOOLS__', '\n'.join(parts))
    script = script.replace('__SHARED_MANIFEST_SHA__', manifest_sha)
    output = ROOT / 'workspace/Server/tpusoc_shared_asic_20261105_v2.sh'
    data = script.replace('\r\n', '\n').encode()
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to replace an existing versioned artifact')
    output.write_bytes(data)
    print('ARTIFACT', output)
    print('BYTES', len(data))
    print('SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
