"""Syntax checks only; no Synopsys native execution is claimed."""
import ast
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
for p in HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
for p in HERE.glob('*.sh'):subprocess.check_call(['bash','-n',str(p)])
if shutil.which('tclsh'):
    for p in HERE.glob('*.tcl'):
        code='set f [open {'+str(p)+'} r];set s [read $f];close $f;if {![info complete $s]} {exit 2};puts COMPLETE\n'
        r=subprocess.run(['tclsh'],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if r.returncode or r.stdout.strip()!=b'COMPLETE' or r.stderr:
            raise ValueError('Tcl syntax incomplete: '+str(p)+' '+r.stderr.decode(errors='replace'))
print('PYTHON_BASH_TCL_SYNTAX_OK; NATIVE_EDA_NOT_RUN')
