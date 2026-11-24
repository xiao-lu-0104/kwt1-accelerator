"""Create an immutable small report-only recovery entry bound to original v1 payload."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    original = ROOT / 'workspace/Server/tpusoc_refresh_dc_20261109_v1.sh'
    if hashlib.sha256(original.read_bytes()).hexdigest() != '4edc335d7c8166ca8afdccecca91d302630f179d6ce7210f94254f97c9c6330b':
        raise ValueError('Frozen DC entry changed')
    payload = base64.b64decode(original.read_text().split("<<'TPUSOC_REFRESH_PAYLOAD'\n", 1)[1].split('\nTPUSOC_REFRESH_PAYLOAD', 1)[0])
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        manifest_sha = hashlib.sha256(archive.extractfile('MANIFEST.sha256').read()).hexdigest()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for path in [HERE / 'Review.py', HERE / 'Review.tcl', ROOT / 'Server/SystemBackend/StageWatch.py']:
            data = path.read_bytes().replace(b'\r\n', b'\n')
            info = tarfile.TarInfo(path.name)
            info.size = len(data)
            info.mtime = 1704067200
            archive.addfile(info, io.BytesIO(data))
    payload = buffer.getvalue()
    entry = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_dc_review_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'TPUSOC_DC_REVIEW_PAYLOAD'
''' + base64.encodebytes(payload).decode() + '''TPUSOC_DC_REVIEW_PAYLOAD
echo "''' + hashlib.sha256(payload).hexdigest() + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "REVIEW_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
python3 -u "$work/Review.py" --manifest-sha ''' + manifest_sha + ''' --out "$work" "$@"
'''
    output = ROOT / 'workspace/Server/tpusoc_dc_review_20261109_v1.sh'
    if output.exists():
        raise ValueError('Refusing to replace versioned review entry')
    output.write_bytes(entry.encode())
    print('ARTIFACT', output)
    print('BYTES', output.stat().st_size)
    print('SHA256', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
