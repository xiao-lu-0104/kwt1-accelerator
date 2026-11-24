"""Verify reset reconvergence and prepare explicit binary-start diagnostics."""
import argparse
import json
from pathlib import Path
import shutil
from ReadCone import select
from ReadProbe import module, instances, bindings, sha


def seed_observer(top, bus, flop):
    base = bus + '.' + flop + (' ' if flop.startswith('\\') else '')
    return '''`timescale 1ns/1ps
// Explicit initial condition for a diagnosed reset X-pessimism case.
// Only Word[0] Q is forced for ONE reset clock, then released permanently.
module @TOP@;
    integer Seed;
    bit Released = 0, Checked = 0;
    initial begin
        if (!$value$plusargs("BOOT_WORD0=%d", Seed) || Seed < 0 || Seed > 1)
            $fatal(1, "BOOT_WORD0 must explicitly select 0 or 1");
        wait (@BUS@.ResetN === 1'b0);
        #0.001;
        $display("BOOT_BEFORE: seed=%0d Word=%b State=%b D0=%b time=%0t", Seed, @BUS@.Word, @BUS@.State, @DATA@, $time);
        if (Seed == 0) force @PIN@ = 1'b0;
        else force @PIN@ = 1'b1;
        #0.001;
        if (@BUS@.ResetN !== 1'b0 || @DATA@ !== 1'b0)
            $fatal(1, "BINARY_START_RESET_D_NOT_ZERO seed=%0d D0=%b", Seed, @DATA@);
        $display("BOOT_RESET_D: seed=%0d D0=%b (all other mapped state left untouched)", Seed, @DATA@);
        @(posedge @BUS@.Clock);
        @(negedge @BUS@.Clock);
        #0.001;
        release @PIN@;
        Released = 1;
        $display("BOOT_RELEASED: seed=%0d time=%0t; no further DUT drive", Seed, $time);
        repeat (2) begin
            @(posedge @BUS@.Clock);
            #0.001;
            if (@BUS@.ResetN !== 1'b0 || @BUS@.Word !== 2'b00 || @BUS@.State !== 3'b000 || @DATA@ !== 1'b0)
                $fatal(1, "POST_RELEASE_RESET_FAILED seed=%0d Word=%b State=%b D0=%b", Seed, @BUS@.Word, @BUS@.State, @DATA@);
        end
        Checked = 1;
        $display("BOOT_RESET_VERIFIED: seed=%0d Word=00 State=000; force released before reset deassertion", Seed);
    end
    always @(posedge @BUS@.ResetN) if (!Released || !Checked)
        $fatal(1, "RESET_RELEASE_PRECEDED_BOOT_CHECK");
    final $display("BOOT_FINAL: seed=%0d released=%b checked=%b", Seed, Released, Checked);
endmodule
'''.replace('@TOP@', top).replace('@BUS@', bus).replace('@PIN@', base + '.Q').replace('@DATA@', base + '.D')


def guard(bus):
    expected = {
        'n552': ('AOA211V1_12TR40', {'A1': 'n177', 'A2': 'n574', 'B': 'Word[0]', 'C': 'n176', 'Z': 'n552'}),
        'n176': ('NAND2CV0_12TR40', {'A1': 'n177', 'A2': 'Word[0]', 'ZN': 'n176'}),
        'n177': ('OAI21V0_12TR40', {'A1': 'n337', 'A2': 'n621', 'B': 'n303', 'ZN': 'n177'}),
        'n303': ('AOI21V0_12TR40', {'A1': 'WriteDataReady', 'A2': 'WriteDataValid', 'B': 'n304', 'ZN': 'n303'}),
        'n304': ('NAND2CV0_12TR40', {'A1': 'n174', 'A2': 'n173', 'ZN': 'n304'}),
        'n174': ('CLKINV0_12TR40', {'I': 'n155', 'ZN': 'n174'}),
        'n155': ('AO1B2V0_12TR40', {'A1': 'RequestReady', 'A2': 'RequestValid', 'B': 'ResetN', 'Z': 'n155'}),
        'n574': ('CLKINV0_12TR40', {'I': 'n623', 'ZN': 'n574'}),
        'n623': ('NAND2CV0_12TR40', {'A1': 'ResetN', 'A2': 'IcbResponseReady', 'ZN': 'n623'}),
    }
    rows = [(ref, name, bindings(ports)) for ref, name, ports in instances(bus)]
    for net, (ref, links) in expected.items():
        if sum(row[0] == ref and row[2] == links for row in rows) != 1:
            raise ValueError('Reset-cone evidence changed: ' + net)
    flops = [name for ref, name, links in rows if ref == 'DQV0_12TR40'
             and links == {'D': 'n552', 'CK': 'Clock', 'Q': 'Word[0]'}]
    if len(flops) != 1:
        raise ValueError('Expected exactly the diagnosed Word[0] FF')
    return flops[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cone', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cone = select(args.cone)
    original = json.loads((cone / 'ConeInputs.json').read_text())
    probe = Path(original['probe'])
    out = args.out.resolve()
    candidate = out / 'candidate.v'
    shutil.copy2(cone / 'candidate.v', candidate)
    flop = guard(module(candidate.read_text(), 'TpuIcb'))
    unit = (cone / 'real.f').read_text().splitlines()
    (out / 'unit.f').write_text('\n'.join(str(candidate) if line == str(cone / 'candidate.v') else line for line in unit) + '\n')
    full = (probe / 'candidate.f').read_text().splitlines()
    (out / 'full.f').write_text('\n'.join(str(candidate) if line == str(probe / 'candidate.v') else line for line in full) + '\n')
    (out / 'UnitResetWordBoot.sv').write_text(seed_observer('UnitResetWordBoot', 'GateIcbSmoke.Dut', flop))
    (out / 'FullResetWordBoot.sv').write_text(seed_observer('FullResetWordBoot', 'SharedTest.Cpu.u_e203_cpu.u_e203_nice_core.Bus', flop))
    for name in ('Bundle.txt', 'Functional.txt'):
        shutil.copy2(probe / name, out / name)
    fingerprints = dict(original['inputs'])
    for name in ('candidate.v', 'UnitResetWordBoot.sv', 'FullResetWordBoot.sv', 'unit.f', 'full.f'):
        path = out / name
        fingerprints[str(path)] = sha(path)
    for line in full:
        if line and not line.startswith(('+', '-')):
            path = Path(line)
            fingerprints[str(path)] = sha(path)
    (out / 'BootInputs.json').write_text(json.dumps({'cone': str(cone), 'inputs': fingerprints,
        'scope': 'Word[0] binary initial condition for one reset clock, released before tasks; no unseeded acceptance'}, indent=2) + '\n')
    print('VERIFIED_CONE:', cone)
    print('RESET_CONE_GUARD: nine mapped gates and actual Word[0] FF connections verified')
    print('RESET_ALGEBRA: ResetN=0 -> n155=1,n174=0,n304=1,n303=0,n177=1,n623=1,n574=0,n176=~Word[0]')
    print('RESET_D0: Word[0] & ~Word[0]; Boolean 0 for both initial values, four-state X for unknown')
    print('SCOPE: explicit binary-start functional diagnostics; candidate and foundry models unchanged; force during one reset clock only')


if __name__ == '__main__':
    main()
