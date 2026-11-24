from pathlib import Path
import hashlib,json,tarfile,tempfile

HERE=Path(__file__).resolve().parent
code=(HERE/'ResumePowerPinInit_6bb1bea.sh').read_text().split("python3 - <<'PIN_INIT_REPAIR'\n",1)[1].split('\nPIN_INIT_REPAIR\n',1)[0]
with tempfile.TemporaryDirectory(prefix='pin_recovery_test_') as directory:
    root=Path(directory)/'power';root.mkdir()
    with tarfile.open(HERE/'payload.before_pin_init_repair.tar.gz') as archive:
        for m in archive:
            if m.isfile():
                p=root/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(m).read())
    (root/'system').mkdir()
    candidate=b'unchanged mapped system candidate fixture\n'
    (root/'system/candidate.v').write_bytes(candidate)
    (root/'system/Complete.json').write_text(json.dumps({'source_commit':'6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6','netlist_sha256':hashlib.sha256(candidate).hexdigest()}))
    (root/'ff1').mkdir();(root/'ff1/native.log').write_text('previous failed boot evidence\n')
    patched=code.replace("Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))",'Path('+repr(str(root))+')')
    exec(compile(patched,'repair_first','exec'),{})
    assert (root/'system/candidate.v').read_bytes()==candidate
    backups=list(root.glob('ff1_failed_before_pin_init_*'))
    assert len(backups)==1 and (backups[0]/'native.log').read_text()=='previous failed boot evidence\n'
    (root/'ff1').mkdir();(root/'ff1/native.log').write_text('new attempt must not be moved on a repeat\n')
    exec(compile(patched,'repair_repeat','exec'),{})
    assert (root/'ff1/native.log').read_text()=='new attempt must not be moved on a repeat\n'
    (root/'system/candidate.v').write_bytes(b'altered candidate')
    try:exec(compile(patched,'repair_negative','exec'),{})
    except AssertionError:print('ALTERED_SYSTEM_CANDIDATE_REJECTED')
    else:raise AssertionError('Changed netlist accepted')
print('PIN_RECOVERY_EXACT_PATCH_BACKUP_RESUME_GUARDS_PASS')
