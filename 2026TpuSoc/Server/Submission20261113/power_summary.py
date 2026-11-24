"""Parse physical units explicitly; never guess a power report unit."""
import math
import re

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
UNITS={'W':1.,'mW':1e-3,'uW':1e-6,'nW':1e-9,'pW':1e-12}


def power_values(text):
    data={}
    for key,label in [('internal_w','Cell Internal Power'),('switching_w','Net Switching Power'),
                      ('dynamic_w','Total Dynamic Power'),('leakage_w','Cell Leakage Power')]:
        m=re.findall(re.escape(label)+r'\s*=\s*('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',text)
        if len(m)!=1:raise ValueError('Missing/ambiguous physical power unit: '+label)
        data[key]=float(m[0][0])*UNITS[m[0][1]]
    if any(not math.isfinite(v) or v<0 for v in data.values()):raise ValueError('Invalid power value')
    if data['dynamic_w']<=0 or abs(data['dynamic_w']-data['internal_w']-data['switching_w'])>max(1e-12,data['dynamic_w']*.01):
        raise ValueError('Dynamic component accounting failed')
    data['total_w']=data['dynamic_w']+data['leakage_w']
    return data


def group_values(text,count):
    matches=re.findall(r'^Totals\s*\(\s*(\d+)\s+cells\s*\)\s*(.*)$',text,re.M)
    if len(matches)!=1 or int(matches[0][0])!=count:raise ValueError('Group cell count mismatch')
    pairs=re.findall(r'('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',matches[0][1])
    if len(pairs)!=4:raise ValueError('Group power requires four explicit units')
    values={k:float(v)*UNITS[u] for k,(v,u) in zip(['internal_w','switching_w','dynamic_w','leakage_w'],pairs)}
    if any(not math.isfinite(v) or v<0 for v in values.values()):raise ValueError('Invalid group power')
    values['total_w']=values['dynamic_w']+values['leakage_w']
    return values
