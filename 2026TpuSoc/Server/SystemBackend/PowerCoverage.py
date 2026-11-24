"""Preserve every labeled SAIF coverage table; never overwrite hierarchy rows."""
import re


def coverage_tables(text):
    tables=[]; current={}; start=None
    lines=text.splitlines()
    for index,line in enumerate(lines):
        match=re.match(r'\s*(Nets|Ports|Pins)\s+(.*)$',line)
        if not match: continue
        values=re.findall(r'(\d+)\s*\(\s*([\d.]+)%\s*\)',match[2])
        tail=re.search(r'\s(\d+)\s*$',match[2])
        if len(values)!=3 or not tail: continue
        key=match[1].lower()
        if key in current: raise ValueError('Repeated object row before SAIF coverage table completed')
        if start is None: start=index
        group={name:{'count':int(value),'percent':float(percent)}
            for name,(value,percent) in zip(('user','default','propagated'),values)}
        group['total']=int(tail[1])
        if sum(group[name]['count'] for name in ('user','default','propagated'))!=group['total']:
            raise ValueError('SAIF coverage count sum mismatch')
        current[key]=group
        if len(current)==3:
            tables.append({'line':start+1,'context':lines[max(0,start-16):start],
                'objects':current})
            current={}; start=None
    if current: raise ValueError('Incomplete SAIF coverage table')
    if not tables: raise ValueError('Missing three-object SAIF coverage summary')
    return tables


def coverage(text):
    tables=coverage_tables(text)
    if len(tables)!=1: raise ValueError('Multiple SAIF coverage tables require explicit hierarchy selection')
    return tables[0]['objects']
