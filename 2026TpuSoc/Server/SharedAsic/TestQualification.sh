#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
build=$(mktemp -d /tmp/tpusoc_qualification_XXXXXX)
echo "LOCAL_QUALIFICATION_BUILD: $build"
python3 "$source_dir/TestQualification.py" --fixtures "$build"
cp "$source_dir/QualificationWindow.sv" "$source_dir/SharedMacroSmoke.sv" "$build/"
cd "$build"
if ! verilator --binary --timing -Wno-fatal --top-module SharedMacroSmoke \
    --Mdir macro_obj SharedMacroSmoke.sv MacroFixture.sv > macro_build.log 2>&1; then
    tail -n 25 macro_build.log; exit 1
fi
./macro_obj/VSharedMacroSmoke > macro_good.log 2>&1
grep '^PASS SHARED_MACRO_SMOKE:' macro_good.log
if (ulimit -c 0; ./macro_obj/VSharedMacroSmoke +BAD_MASK) > macro_bad.log 2>&1; then
    echo 'ERROR: reversed mask fixture accepted'; exit 1
fi
grep -q 'SHARED_MACRO_READ' macro_bad.log
echo 'PASS LOCAL_MACRO_NEGATIVE: inverted mask rejected'
if ! verilator --binary --timing -Wno-fatal --top-module LocalQualificationTop \
    --Mdir guard_obj QualificationWindow.sv EffectiveDataGuard.sv candidate.sv Fixture.sv > guard_build.log 2>&1; then
    tail -n 35 guard_build.log; exit 1
fi
./guard_obj/VLocalQualificationTop > guard_good.log 2>&1
grep -E '^(PASS EFFECTIVE|PASS LOCAL_QUALIFICATION)' guard_good.log
if (ulimit -c 0; ./guard_obj/VLocalQualificationTop +EMPTY_DOT) > guard_empty.log 2>&1; then
    echo 'ERROR: unexercised DOT guard accepted'; exit 1
fi
grep -q 'UNEXERCISED_EFFECTIVE_GUARD' guard_empty.log
echo 'PASS LOCAL_GUARD_NEGATIVE: unexercised consumer rejected; four-state X behavior requires server VCS'
