"""Read existing task SAIF/reports and classify unresolved activity, without EDA runs."""
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from ReadProbe import instances, bindings

TOKEN=re.compile(r'(?P<SPACE>\s+)|(?P<BOM>\ufeff)|'
    r'(?P<COMMENT>/\*.*?\*/|//[^\r\n]*)|(?P<OPEN>\()|(?P<CLOSE>\))|'
    r'(?P<STRING>"(?:\\.|[^"\\])*")|(?P<ATOM>(?:\\.|[^()\s"\ufeff])+)',re.S)
ROOT=('SharedTest','Cpu','u_e203_cpu','u_e203_nice_core')
TASKS={'ff1':(332348,0.002215764116),'encoder':(1485712,0.009905241904)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def name(token):
    if token.startswith('"') and token.endswith('"'): token=token[1:-1]
    return re.sub(r'\\(.)',r'\1',token).strip().lstrip('\\')


def parse_error(text,position,reason):
    line=text.count('\n',0,position)+1
    column=position-text.rfind('\n',0,position)
    context=text[max(0,position-70):min(len(text),position+130)]
    return ValueError(f'{reason}; offset={position} line={line} column={column} context={context!r}')


def tokens(text,ignored):
    """Skip only whitespace, a leading BOM, and explicit C/C++ comments.

    Strings and escaped identifiers are kept intact. Unsupported outside text
    remains an error; it is never treated as an arbitrary ignorable banner.
    """
    position=0
    while position<len(text):
        if text.startswith('/*',position) and text.find('*/',position+2)<0:
            raise parse_error(text,position,'Unterminated SAIF block comment')
        match=TOKEN.match(text,position)
        if not match: raise parse_error(text,position,'Invalid or unterminated SAIF token')
        position=match.end()
        kind=match.lastgroup
        if kind=='SPACE': continue
        if kind=='BOM':
            if match.start()!=0: raise parse_error(text,match.start(),'BOM inside SAIF body')
            ignored.append((match.start(),match.end(),kind))
            continue
        if kind=='COMMENT':
            ignored.append((match.start(),match.end(),kind))
            continue
        # Exclude quoted header/name text from the independent raw TX scan.
        if kind=='STRING': ignored.append((match.start(),match.end(),kind))
        yield match


def hierarchy(text):
    modules={m[1]:m[0] for m in re.finditer(
        r'(?m)^\s*module\s+([A-Za-z_]\w*)\b.*?\bendmodule\b',text,re.S)}
    leaves={}
    def walk(ref,scope,chain):
        if ref in chain: raise ValueError('Recursive mapped hierarchy')
        for cell,instance,ports in instances(modules[ref]):
            # Verilog escaped identifiers begin with backslash, unlike SAIF's
            # per-character escapes. Keep generated-scope dots inside the name.
            identifier=instance[1:] if instance.startswith('\\') else instance
            where=scope+(identifier.strip(),)
            if cell in modules: walk(cell,where,chain+(ref,))
            else: leaves[where]={'ref':cell,'bindings':bindings(ports)}
    walk('e203_subsys_nice_core',ROOT,())
    if not leaves: raise ValueError('Mapped leaf inventory is empty')
    if sum(v['ref']=='RAMSP1024X16' for v in leaves.values())!=56:
        raise ValueError('Reviewed candidate must contain 56 private SRAMs')
    return leaves


def classify(scope,kind,signal,leaves):
    prefix=scope
    while prefix and prefix not in leaves: prefix=prefix[:-1]
    if not prefix:
        return 'mapped_hierarchy_'+kind.lower(),'',None
    ref=leaves[prefix]['ref']
    if prefix!=scope or kind!='PORT': return 'library_model_internal',ref,prefix
    if ref=='RAMSP1024X16': return 'private_sram_port',ref,prefix
    if signal in ('Q','QN') and re.match(r'(?:DQ|SDQ|DF|DFF)',ref,re.I):
        return 'mapped_ff_output',ref,prefix
    return 'mapped_leaf_port',ref,prefix


def saif_review(text,leaves):
    stack=[]
    unknown=[]
    clock_profiles=Counter()
    clock_examples=[]
    tx_count=0
    unmapped_tx=0
    signal_count=0
    duration=None
    scale=None
    ignored=[]
    roots=0
    for match in tokens(text,ignored):
        token=match[0]
        if token=='(':
            if not stack:
                roots+=1
                if roots!=1: raise parse_error(text,match.start(),'Multiple SAIF root expressions')
            signal=bool(stack and stack[-1]['head'] in ('NET','PORT'))
            stack.append({'head':None,'atoms':[],'signal':signal,'stats':{},'tx':[]})
        elif token==')':
            if not stack: raise parse_error(text,match.start(),'SAIF close without open')
            frame=stack.pop()
            head=frame['head']
            if head is None: raise parse_error(text,match.start(),'Empty SAIF expression')
            if not stack and head!='SAIFILE': raise parse_error(text,match.start(),'Expected SAIFILE root')
            if head=='DURATION': duration=float(frame['atoms'][0])
            if head=='TIMESCALE': scale=frame['atoms']
            if head in ('T0','T1','TX','TZ','TC','IG'):
                value=float(frame['atoms'][0])
                if stack and stack[-1]['signal']: stack[-1]['stats'][head]=value
                if head=='TX':
                    tx_count+=1
                    target=next((f for f in reversed(stack) if f['signal']),None)
                    if target is None: unmapped_tx+=1
                    else: target['tx'].append(value)
            if frame['signal']:
                signal_count+=1
                # INSTANCE may include an optional quoted cell type before its name.
                scope=tuple(name(f['atoms'][-1]) for f in stack if f['head']=='INSTANCE' and f['atoms'])
                signal=name(head)
                kind=stack[-1]['head']
                category,ref,leaf=classify(scope,kind,signal,leaves)
                if any(v>0 for v in frame['tx']):
                    unknown.append({'scope':'/'.join(scope),'signal':signal,'kind':kind,
                        'category':category,'ref':ref,'TX':max(frame['tx']),
                        'nonzero_TX_records':sum(v>0 for v in frame['tx']),
                        'TC':frame['stats'].get('TC'),'leaf':'/'.join(leaf) if leaf else ''})
                if re.fullmatch(r'(?i)(?:clock|clk|ck|cp|nice_clk)',signal):
                    stats=frame['stats']
                    key=(category,ref,signal,stats.get('TC'),stats.get('TX'),stats.get('T1'))
                    clock_profiles[key]+=1
                    if scope==ROOT or (ref=='RAMSP1024X16' and len(clock_examples)<12):
                        clock_examples.append({'scope':'/'.join(scope),'signal':signal,'stats':stats})
        else:
            if not stack: raise parse_error(text,match.start(),f'SAIF atom outside expression: {token!r}')
            if stack[-1]['head'] is None: stack[-1]['head']=token
            else: stack[-1]['atoms'].append(token)
    if stack or not duration or not scale: raise ValueError('Truncated SAIF or missing time header')
    # Count every TX record, including conditional library records; never discard
    # an unknown because the path could not be associated with a physical leaf.
    starts=[span[0] for span in ignored]
    regex_tx=0
    for match in re.finditer(r'\(TX\s+',text):
        index=bisect_right(starts,match.start())-1
        if index<0 or match.start()>=ignored[index][1]: regex_tx+=1
    if tx_count!=regex_tx or unmapped_tx:
        raise ValueError(f'SAIF TX parse incomplete: parsed={tx_count}, regex={regex_tx}, unmapped={unmapped_tx}')
    unit={'fs':1e-15,'ps':1e-12,'ns':1e-9,'us':1e-6,'ms':1e-3,'s':1}
    seconds=duration*float(scale[0])*unit[scale[1].lower()]
    for row in unknown: row['TX_fraction']=row['TX']/duration
    groups=Counter((r['category'],r['ref']) for r in unknown)
    blocks=Counter('/'.join(r['scope'].split('/')[len(ROOT):len(ROOT)+3]) or '<top>' for r in unknown)
    profiles=[{'category':key[0],'ref':key[1],'signal':key[2],'TC':key[3],
        'TX':key[4],'T1':key[5],'objects':count} for key,count in clock_profiles.most_common()]
    return {'duration_seconds':seconds,'signals':signal_count,'TX_records':tx_count,
        'ignored_comments':sum(span[2]=='COMMENT' for span in ignored),
        'unknown_signals':len(unknown),'nonzero_TX_records':sum(r['nonzero_TX_records'] for r in unknown),
        'unknown_groups':[{'category':key[0],'ref':key[1],'objects':count} for key,count in groups.most_common()],
        'unknown_blocks':dict(blocks.most_common()),'clock_profiles':profiles,'clock_examples':clock_examples,
        'unknown':unknown,'acceptance':'Classification only; no unknown waived as harmless'}


def select(previous):
    choices=[previous.resolve()] if previous else sorted(
        (Path.home()/'soc').glob('tpusoc_task_power_20261105_*'),
        key=lambda p:p.stat().st_mtime,reverse=True)
    for run in choices:
        try:
            record=json.loads((run/'TaskPowerInputs.json').read_text())
            for filename,digest in record['inputs'].items():
                if sha(Path(filename))!=digest: raise ValueError('Frozen input changed: '+filename)
            if 'RESULT: TASK_POWER_COLLECTION_COMPLETE' not in (run/'runner.log').read_text():
                raise ValueError('Task collection incomplete')
            summary=json.loads((run/'TaskPowerSummary.json').read_text())
            tasks={row['task']:row for row in summary['tasks']}
            for task,(cycles,duration) in TASKS.items():
                case=run/task
                if (case/'dc_status.txt').read_text().strip()!='PASS': raise ValueError('Power tool did not pass')
                if tasks[task]['cycles']!=cycles or abs(tasks[task]['duration_seconds']-duration)>2e-12:
                    raise ValueError('Task window mismatch')
                if sha(case/'task.saif')!=tasks[task]['sha256']: raise ValueError('Task SAIF changed')
                log=(case/'run.log').read_text(errors='replace')
                for required in ('PASS SHARED:','INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0',
                    'ICB_MIRROR_FINAL: divergence_observed=0','TASK_ACTIVITY_FINAL: started=1 stopped=1'):
                    if required not in log: raise ValueError('Original functional guard missing')
                if re.search(r'Fatal:|FATAL:|Error-\[',log): raise ValueError('Original task failed')
            return run,record,summary
        except (OSError,ValueError,KeyError):
            if previous: raise
    raise ValueError('No unchanged completed task-power run found')


def report_excerpt(path,limit=72):
    if not path.exists():
        print('REPORT_NOT_PRESENT:',path)
        return
    lines=path.read_text(errors='replace').splitlines()
    print('REPORT_EXCERPT_BEGIN:',str(path),'lines='+str(len(lines)))
    if len(lines)>limit:
        print('\n'.join(lines[:limit-12]+['... full file retained ...']+lines[-12:]))
    else: print('\n'.join(lines))
    print('REPORT_EXCERPT_END')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run,record,summary=select(args.run)
    out=args.out.resolve()
    leaves=hierarchy((run/'candidate.v').read_text())
    inputs=dict(record['inputs'])
    print('VERIFIED_COMPLETED_TASK_POWER:',run)
    print('MODE: existing SAIF/netlist/report read only; no VCS, DC, resynthesis or activity override')
    result={'source':str(run),'tasks':{},'system_power':'PENDING_CPU_INTERCONNECT_SHARED_SRAM'}
    for task in TASKS:
        case=run/task
        raw=(case/'task.saif').read_text()
        try:
            review=saif_review(raw,leaves)
        except (ValueError,IndexError,KeyError) as error:
            print('SAIF_PARSE_DIAGNOSTIC_FILE:',case/'task.saif')
            print('SAIF_HEADER_REPR:',repr(raw[:1200]))
            print('SAIF_TRAILER_REPR:',repr(raw[-200:]))
            raise ValueError(str(error)) from error
        if abs(review['duration_seconds']-TASKS[task][1])>2e-12: raise ValueError('Parsed SAIF duration changed')
        old=next(row for row in summary['tasks'] if row['task']==task)
        if review['nonzero_TX_records']!=old['TX_nonzero_entries']:
            raise ValueError('Unknown inventory differs from original TX scan')
        if review['TX_records']!=old['TX_entries']:
            raise ValueError('TX inventory differs from original scan; review retained file/header diagnostics')
        result['tasks'][task]=review
        (out/(task+'_review.json')).write_text(json.dumps(review,indent=2)+'\n')
        print('ACTIVITY_REVIEW_TASK:',task,'TX_records='+str(review['TX_records']),
            'unknown_signals='+str(review['unknown_signals']),'nonzero_TX_records='+str(review['nonzero_TX_records']),
            'comments_ignored='+str(review['ignored_comments']))
        for group in review['unknown_groups'][:14]: print('UNKNOWN_GROUP:',task,json.dumps(group,sort_keys=True))
        for block,count in list(review['unknown_blocks'].items())[:10]: print('UNKNOWN_BLOCK:',task,count,block)
        for profile in review['clock_profiles'][:8]: print('CLOCK_PROFILE:',task,json.dumps(profile,sort_keys=True))
        for row in review['clock_examples'][:4]: print('CLOCK_EXAMPLE:',task,json.dumps(row,sort_keys=True))
        # Prioritize mapped FF outputs, macro ports and mapped hierarchy nets.
        examples=sorted(review['unknown'],key=lambda row:(row['category']=='library_model_internal',-row['TX_fraction'],row['scope'],row['signal']))
        for row in examples[:12]: print('UNKNOWN_EXAMPLE:',task,json.dumps(row,sort_keys=True))
        report_excerpt(case/'saif_missing.rpt')
        log=(case/'dc.log').read_text(errors='replace').splitlines()
        selected=set()
        for i,line in enumerate(log):
            if re.search(r'conflict|PWR-19|not found|unannotated|cannot annotate|failed to annotate',line,re.I):
                selected.update(range(max(0,i-2),min(len(log),i+4)))
        print('ANNOTATION_CONFLICT_CONTEXT_BEGIN:',task)
        for i in sorted(selected)[:48]: print(log[i])
        print('ANNOTATION_CONFLICT_CONTEXT_END')
        for path in case.iterdir():
            if path.is_file() and path.suffix in ('.saif','.rpt','.log','.json','.txt'):
                inputs[str(path)]=sha(path)
    preflight=Path(record['preflight'])
    print('INSTALLED_HELP_REVIEW_BEGIN')
    for command in ('read_saif','report_saif','report_switching_activity'):
        path=preflight/'help'/(command+'_manual.txt')
        if not path.exists(): continue
        inputs[str(path)]=sha(path)
        lines=path.read_text(errors='replace').splitlines()
        selected=set()
        for i,line in enumerate(lines):
            if re.search(r'conflict|missing|clock|report_activity|get_switching_activity',line,re.I):
                selected.update(range(max(0,i-2),min(len(lines),i+5)))
        print('HELP_SOURCE:',command)
        for i in sorted(selected)[:32]: print(lines[i])
    print('INSTALLED_HELP_REVIEW_END')
    context=json.loads((run/'SystemPowerContext.json').read_text())
    print('PLATFORM_MEMORY_EVIDENCE_BEGIN')
    for item in context['platform_files']:
        path=Path(item['path'])
        if sha(path)!=item['sha256']: raise ValueError('Platform memory input changed')
        text=path.read_text(errors='replace')
        print('PLATFORM_SOURCE:',path)
        decls=re.findall(r'(?m)^\s*(?:input|output|parameter|localparam)\b[^;]*;',text)
        print('\n'.join(' '.join(s.split()) for s in decls[:15]))
        for line in text.splitlines():
            if re.search(r'\bsirv_(?:sim|gnrl)_ram\b|\.(?:DW|AW|DP|MW)\s*\(',line): print(line.strip())
    print('PLATFORM_MEMORY_EVIDENCE_END')
    catalog=context['memory_catalog']['available_sram_packages']
    print('SYSTEM_SRAM_1P1V_25C_CANDIDATES_BEGIN')
    for item in catalog:
        root=Path(item['directory'])
        for path in sorted(root.glob('lib/*_tt_1p10v_1p10v_25c.lib')):
            inputs[str(path)]=sha(path)
            raw=path.read_text(errors='replace')
            cells=re.findall(r'\bcell\s*\(\s*(\w+)\s*\)',raw)
            print('SYSTEM_SRAM_MODEL:',path,'cells='+','.join(cells),'sha256='+inputs[str(path)])
    print('SYSTEM_SRAM_1P1V_25C_CANDIDATES_END')
    for path in (run/'TaskPowerInputs.json',run/'TaskPowerSummary.json',run/'SystemPowerContext.json',run/'runner.log'):
        inputs[str(path)]=sha(path)
    (out/'ReviewInputs.json').write_text(json.dumps({'source':str(run),'inputs':inputs},indent=2)+'\n')
    (out/'ActivityReviewSummary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('REVIEW_ACCEPTANCE: pending object-level review and CPU/interconnect/shared SRAM estimate; no unknown or missing activity waived')


if __name__=='__main__': main()
