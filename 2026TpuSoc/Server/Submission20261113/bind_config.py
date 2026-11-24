"""Merge an explicitly reviewed frontend description with native-tested PDK paths.

The frontend description is authored only after the new commit is published.
No top/module names or macro inventory are inferred from the previous design.
"""
import argparse
from pathlib import Path
from evaluate import load,save


def main():
    p=argparse.ArgumentParser();p.add_argument('--frontend-description',type=Path,required=True)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--pdk',type=Path,required=True)
    p.add_argument('--topology-review',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();d=load(a.frontend_description);pdk=load(a.pdk);review=load(a.topology_review)
    if not d.get('frontend_bound') or d['source_commit']!=review['source_commit']:
        raise ValueError('Wait for actual new frontend review')
    d.update(pdk);d['source_root']=str(a.source_root.resolve());d['topology_review']=str(a.topology_review.resolve())
    save(a.out,d);print('SERVER_CONFIG_WRITTEN',a.out,'; run flow.py preflight next')


if __name__=='__main__':main()
