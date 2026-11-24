"""Read existing probe netlists/models/logs; no synthesis or simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(text, name):
    match = re.search(r'\bmodule\s+' + re.escape(name) + r'\b.*?\bendmodule\b', text, re.S)
    if not match:
        raise ValueError('Module not found: ' + name)
    return match[0]


def balanced(text, start):
    depth = 0
    for index in range(start, len(text)):
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return text[start:index+1]
    raise ValueError('Unbalanced instance connection')


def instances(text):
    for match in re.finditer(r'(?m)^\s*([A-Za-z_]\w*)\s+(\\[^\s]+|[A-Za-z_]\w*)\s*\(', text):
        if match[1] in ('module', 'if', 'for', 'while', 'case'):
            continue
        opening = text.find('(', match.start())
        yield match[1], match[2], balanced(text, opening)


def bindings(text):
    result = {}
    for match in re.finditer(r'\.([A-Za-z_]\w*)\s*\(', text):
        opening = text.find('(', match.start())
        result[match[1]] = balanced(text, opening)[1:-1].strip()
    return result


def declarations(text):
    result = []
    for match in re.finditer(r'\b(input|output|inout)\b\s+([^;]+);', text):
        result.append(match[1] + ' ' + ' '.join(match[2].split()) + ';')
    return result


def input_names(text):
    names = []
    for declaration in declarations(text):
        if not declaration.startswith('input '):
            continue
        fields = re.sub(r'\[[^\]]*\]|\b(?:input|wire|reg|logic|signed)\b', '', declaration).strip(' ;')
        names += [field.strip() for field in fields.split(',')]
    return names


def select(previous):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home() / 'soc').glob('tpusoc_gate_probe_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in choices:
        try:
            record = json.loads((path / 'ProbeInputs.json').read_text())
            if 'RESULT: GATE_PROBE_COMPLETE' not in (path / 'runner.log').read_text():
                raise ValueError('Probe not complete')
            for name, expected in record['inputs'].items():
                if sha(Path(name)) != expected:
                    raise ValueError('Probe input changed: ' + name)
            return path, record
        except (OSError, ValueError, KeyError):
            if previous:
                raise
    raise ValueError('No unchanged completed probe found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path, nargs='?')
    args = parser.parse_args()
    probe, record = select(args.probe)
    print('READ_ONLY_PROBE:', probe)
    candidate = (probe / 'candidate.v').read_text()
    top = module(candidate, 'e203_subsys_nice_core')
    bus_instances = [row for row in instances(top) if row[1] == 'Bus']
    if len(bus_instances) != 1:
        raise ValueError('Expected one Bus instance')
    bus_type, _, connections = bus_instances[0]
    bus = module(candidate, bus_type)
    print('BUS_TYPE:', bus_type)
    print('BUS_CONNECTIONS_BEGIN')
    for name, value in bindings(connections).items():
        print(name + ' = ' + value)
    print('BUS_CONNECTIONS_END')
    print('BUS_PORTS_BEGIN')
    print('\n'.join(declarations(bus)))
    print('BUS_PORTS_END')
    print('SIZE_NETLIST_LINES_BEGIN')
    for scope, text in [('top', top), ('bus', bus)]:
        for line in text.splitlines():
            if re.search(r'nice_icb_cmd_size|IcbCommandSize', line):
                print(scope + ': ' + line.strip())
    print('SIZE_NETLIST_LINES_END')
    models = [Path(name).read_text(errors='replace') for name in record['inputs']
              if '/models/' in name.replace('\\', '/')]
    control = [row for row in instances(bus) if re.search(r'State|Word|Direction|Invalid|BeatError|PacketError', row[1])]
    print('CONTROL_INSTANCES_BEGIN')
    for reference, name, ports in control[:18]:
        print(reference + ' ' + name + ' ' + ports.replace('\n', ' '))
    print('CONTROL_INSTANCES_END')
    refs = sorted({row[0] for row in control})
    for reference in refs:
        found = None
        for text in models:
            try:
                found = module(text, reference)
                break
            except ValueError:
                continue
        if found is None:
            print('MODEL_DEFINITION_MISSING:', reference)
            continue
        print('CONTROL_MODEL_BEGIN:', reference)
        # Sequential functional logic and complete port declarations precede specify.
        body = re.split(r'\bspecify\b', found, maxsplit=1)[0]
        print('\n'.join(body.splitlines()[:65]))
        print('CONTROL_MODEL_END:', reference)
        for ref, name, ports in control:
            if ref != reference:
                continue
            connected = bindings(ports)
            missing = [pin for pin in input_names(found) if not connected.get(pin)]
            if missing:
                print('RAW_UNBOUND_MODEL_INPUT:', name, ','.join(missing), '(check preprocessor guards)')
    print('COMPILE_WARNINGS_BEGIN')
    count = 0
    for mode in ('baseline', 'candidate', 'bus_rtl_control'):
        lines = (probe / mode / 'compile.log').read_text(errors='replace').splitlines()
        for index, line in enumerate(lines):
            if re.search(r'Warning-\[|Error-\[', line):
                print(mode + ': ' + '\n'.join(lines[index:index+5]))
                count += 1
                if count >= 10:
                    break
        if count >= 10:
            break
    print('COMPILE_WARNINGS_END')
    for mode in ('baseline', 'candidate', 'bus_rtl_control'):
        text = (probe / mode / 'ff1.log').read_text(errors='replace')
        print('CASE_LOG:', mode, 'bytes=' + str(len(text)),
              'has_pass=' + str('PASS SHARED:' in text),
              'has_fatal=' + str('Fatal:' in text),
              'has_final=' + str('DIAG_FINAL:' in text))
        if mode == 'bus_rtl_control':
            print('HYBRID_LOG_TAIL:')
            print('\n'.join(text.splitlines()[-8:]))
    print('RESULT: READ_ONLY_PROBE_COMPLETE')


if __name__ == '__main__':
    main()
