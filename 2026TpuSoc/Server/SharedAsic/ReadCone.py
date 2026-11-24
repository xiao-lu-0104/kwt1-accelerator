"""Read first-X evidence and complete Word next-state cone without EDA tools."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(previous):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home() / 'soc').glob('tpusoc_gate_cone_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in choices:
        try:
            record = json.loads((path / 'ConeInputs.json').read_text())
            if 'RESULT: GATE_CONE_DIAGNOSTICS_COMPLETE' not in (path / 'runner.log').read_text():
                raise ValueError('Cone run not complete')
            for name, expected in record['inputs'].items():
                if digest(Path(name)) != expected:
                    raise ValueError('Input changed: ' + name)
            # Reuse the exact checked parser embedded in the completed run.
            for line in (path / 'tools/MANIFEST.sha256').read_text().splitlines():
                expected, name = line.split(None, 1)
                if digest(path / 'tools' / name.strip()) != expected:
                    raise ValueError('Diagnostic tool changed: ' + name)
            return path
        except (OSError, ValueError, KeyError):
            if previous:
                raise
    raise ValueError('No completed, unchanged cone diagnostic found')


def names(body, direction, parser):
    result = []
    for line in parser.declarations(body):
        if line.startswith(direction + ' '):
            fields = re.sub(r'\[[^\]]*\]|\b(?:input|output|wire|reg|logic|signed)\b', '', line).strip(' ;')
            result.extend(part.strip() for part in fields.split(','))
    return list(dict.fromkeys(result))


def first_x_context(text):
    lines = text.splitlines()
    match = next((index for index, line in enumerate(lines)
                  if re.search(r'^CONE_POST:.*(?:state|word)=[01xz]*[xz]', line)), None)
    if match is None:
        return '\n'.join(lines[-12:])
    # Each clock group has PRE, eight D/Q lines and POST. Include previous state.
    return '\n'.join(lines[max(0, match - 22):match + 2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, nargs='?')
    args = parser.parse_args()
    run = select(args.run)
    spec = importlib.util.spec_from_file_location('checked_read_probe', run / 'tools/ReadProbe.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    bus = reader.module((run / 'candidate.v').read_text(), 'TpuIcb')
    models = json.loads((run / 'BusModels.json').read_text())
    print('READ_ONLY_CONE:', run)
    print('MODE: existing logs, candidate connections and saved models only; no simulation or synthesis')
    for case in ('real', 'functional', 'nba_diagnostic'):
        text = (run / case / 'run.log').read_text(errors='replace')
        print('FIRST_X_CONTEXT_BEGIN:', case)
        print(first_x_context(text))
        print('FIRST_X_CONTEXT_END:', case)
        markers = [line for line in text.splitlines() if line.startswith('CELL_XSOURCE:')]
        print('XSOURCE_MARKERS:', case, len(markers))
        print('\n'.join(markers[:16]))
    inputs = set(names(bus, 'input', reader))
    drivers = defaultdict(list)
    for ref, instance, ports in reader.instances(bus):
        links = reader.bindings(ports)
        ins, outs = names(models[ref], 'input', reader), names(models[ref], 'output', reader)
        row = (ref, instance, links, ins, outs)
        for pin in outs:
            if links.get(pin):
                drivers[links[pin]].append(row)
    assignments = dict(re.findall(r'\bassign\s+([^=;]+?)\s*=\s*([^;]+);', bus))
    seeds = []
    for rows in drivers.values():
        for ref, instance, links, ins, outs in rows:
            if re.search(r'Word_reg', instance) and 'D' in links:
                seeds.append(links['D'])
    seeds = list(dict.fromkeys(seeds))
    if not seeds:
        raise ValueError('No Word next-state seeds')
    visited, used_models = set(), set()
    print('WORD_CONE_BEGIN: seeds=' + ','.join(seeds))

    def visit(net, chain):
        if net in chain:
            print('COMBINATIONAL_CYCLE:', ' -> '.join(chain + [net]))
            return
        if net in visited:
            return
        visited.add(net)
        if len(visited) > 500:
            raise ValueError('Unexpectedly large Word cone; stop instead of truncating')
        if net in assignments:
            print('CONE_ASSIGN:', net, '=', assignments[net])
            visit(assignments[net], chain + [net])
        elif net in drivers:
            if len(drivers[net]) > 1:
                print('CONE_MULTIPLE_DRIVERS:', net, len(drivers[net]))
            for ref, instance, links, ins, outs in drivers[net]:
                print('WORD_GATE:', net, '<-', ref, instance, links)
                used_models.add(ref)
                missing = [pin for pin in ins if not links.get(pin)]
                if missing:
                    print('RAW_UNBOUND_INPUT:', instance, ','.join(missing), '(conditional declarations require review)')
                if 'CK' in ins:
                    print('SEQUENTIAL_BOUNDARY:', instance)
                    continue
                for pin in ins:
                    if links.get(pin):
                        visit(links[pin], chain + [net])
        elif net in inputs or re.fullmatch(r'(?:State|Word)\[\d+\]', net):
            print('CONE_BOUNDARY:', net)
        elif re.fullmatch(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+", net):
            print('CONE_CONSTANT:', net)
        else:
            print('CONE_UNRESOLVED_EXPRESSION:', repr(net), '(inspect before inferring undriven)')

    for seed in seeds:
        visit(seed, [])
    print('WORD_CONE_END')
    for ref in sorted(used_models):
        # Preserve primitives, assigns and directives, omit timing arcs and empty/comment lines.
        body = re.split(r'\bspecify\b', models[ref], maxsplit=1)[0]
        body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
        lines = [line.strip() for line in body.splitlines() if line.strip() and not line.lstrip().startswith('//')]
        print('WORD_MODEL_BEGIN:', ref)
        print('\n'.join(lines))
        print('WORD_MODEL_END:', ref)
    print('RESULT: READ_ONLY_CONE_COMPLETE')


if __name__ == '__main__':
    main()
