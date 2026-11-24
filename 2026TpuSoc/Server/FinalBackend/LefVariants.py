"""Compare a plain/antenna LEF pair without changing either source file.

Only recognized pin-antenna statements may be omitted for the comparison. All
other tokens, including geometry, pins, PG uses, sites and obstructions, must match.
This is a conservative selection check, not a complete LEF parser or signoff.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PIN_ANTENNA = set('ANTENNAMODEL ANTENNADIFFAREA ANTENNAGATEAREA ANTENNAMAXAREACAR '
    'ANTENNAMAXSIDEAREACAR ANTENNAMAXCUTCAR ANTENNAPARTIALMETALAREA '
    'ANTENNAPARTIALMETALSIDEAREA ANTENNAPARTIALCUTAREA ANTENNAINPUTGATEAREA '
    'ANTENNAINOUTDIFFAREA ANTENNAOUTPUTDIFFAREA'.split())
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*|[();]|[^\s"();#]+')
FORBIDDEN_BODY = set('MACRO PIN END PORT OBS SIZE RECT POLYGON PATH VIA DIRECTION USE SHAPE PROPERTY'.split())


def tokens(text):
    result, end = [], 0
    for match in TOKEN.finditer(text):
        if text[end:match.start()].strip():
            raise ValueError('Unsupported or unterminated LEF token')
        end = match.end()
        if not match[0].startswith('#'):
            result.append(match[0])
        if len(result) > 2000000:
            raise ValueError('LEF token count exceeds the bounded comparison')
    if text[end:].strip():
        raise ValueError('Unsupported trailing LEF token')
    return result


def non_antenna_tokens(text):
    source = tokens(text)
    kept, removed = [], {}
    macro = pin = None
    start, index = True, 0
    while index < len(source):
        token = source[index]
        following = source[index + 1] if index + 1 < len(source) else None
        if start and token == 'MACRO' and following:
            macro = following
            kept.extend([token, following])
            index += 2
            start = True
            continue
        if start and token == 'PIN' and macro and following:
            pin = following
            kept.extend([token, following])
            index += 2
            start = True
            continue
        if token == 'END' and following in (pin, macro) and following is not None:
            if following == pin:
                pin = None
            else:
                macro = None
            kept.extend([token, following])
            index += 2
            start = True
            continue
        if start and pin and token in PIN_ANTENNA:
            stop = index + 1
            while stop < len(source) and source[stop] != ';':
                if source[stop] in FORBIDDEN_BODY or source[stop].startswith('"') or stop - index > 512:
                    raise ValueError('Malformed or unsupported pin antenna statement: ' + token)
                stop += 1
            if stop == len(source):
                raise ValueError('Unterminated pin antenna statement: ' + token)
            removed[token] = removed.get(token, 0) + 1
            index = stop + 1
            start = True
            continue
        kept.append(token)
        start = token in (';', 'PORT', 'OBS', 'END')
        index += 1
    if macro is not None or pin is not None:
        raise ValueError('Unclosed macro or pin in LEF comparison')
    return kept, removed


def read(path, expected):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Expected bounded regular LEF file: ' + str(path))
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('LEF differs from the previously inspected SHA: ' + str(path))
    return data.decode('utf-8')


def compare(regular, antenna, expected_regular, expected_antenna):
    if regular.parent != antenna.parent or antenna.name != regular.stem + '_ant.lef' or regular.suffix != '.lef':
        raise ValueError('Expected an exact same-directory plain/_ant LEF pair')
    plain, plain_removed = non_antenna_tokens(read(regular, expected_regular))
    enhanced, enhanced_removed = non_antenna_tokens(read(antenna, expected_antenna))
    proof = {'regular': str(regular), 'antenna': str(antenna), 'selected': str(antenna),
             'regular_sha256': expected_regular, 'antenna_sha256': expected_antenna,
             'regular_antenna_statements': plain_removed, 'enhanced_antenna_statements': enhanced_removed,
             'regular_non_antenna_tokens': len(plain), 'enhanced_non_antenna_tokens': len(enhanced),
             'limitations': 'Only recognized pin antenna statements excluded; native workspace checks still required'}
    if plain != enhanced:
        first = next((i for i, (left, right) in enumerate(zip(plain, enhanced)) if left != right), min(len(plain), len(enhanced)))
        proof.update(status='REJECTED_NON_ANTENNA_DIFFERENCE', first_difference_index=first,
                     regular_context=plain[max(0, first-4):first+5], antenna_context=enhanced[max(0, first-4):first+5])
    elif not plain or 'MACRO' not in plain:
        raise ValueError('Empty or non-macro LEF comparison is not accepted')
    else:
        proof.update(status='NON_ANTENNA_TOKENS_IDENTICAL',
                     non_antenna_sha256=hashlib.sha256(json.dumps(plain, separators=(',', ':')).encode()).hexdigest())
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regular', type=Path, required=True)
    parser.add_argument('--antenna', type=Path, required=True)
    parser.add_argument('--regular-sha', required=True)
    parser.add_argument('--antenna-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(args.regular, args.antenna, args.regular_sha, args.antenna_sha)
    except (OSError, ValueError) as error:
        result = {'status': 'LEF_VARIANT_CHECK_FAILED', 'error': str(error)}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('LEF_VARIANT_REVIEW:', json.dumps(result, sort_keys=True), flush=True)
    return 0 if result['status'] == 'NON_ANTENNA_TOKENS_IDENTICAL' else 2


if __name__ == '__main__':
    sys.exit(main())
