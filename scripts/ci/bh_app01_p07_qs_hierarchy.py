#!/usr/bin/env python3
"""P07 HF02 hosted API36 hierarchy verifier: only locate Cancel, never Update."""
import argparse,re,sys,xml.etree.ElementTree as ET
from pathlib import Path

def parse(path):
    b=Path(path).read_bytes()
    if not (16 <= len(b) <= 2_000_000): raise ValueError('missing/oversized UI hierarchy')
    root=ET.fromstring(b)
    if root.tag!='hierarchy':raise ValueError('unexpected hierarchy root')
    nodes=list(root.iter('node'))
    if not any(n.get('text')=='Update Bindhosts rules?' for n in nodes):
        raise ValueError('expected real QS confirmation not visible')
    cancel=[n for n in nodes if n.get('text','').strip().lower()=='cancel']
    if len(cancel)!=1: raise ValueError('missing or ambiguous Cancel button')
    node=cancel[0]
    if node.get('clickable')!='true' or node.get('enabled')!='true':
        raise ValueError('Cancel button not enabled/clickable')
    bounds=node.get('bounds','')
    match=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',bounds)
    if not match:raise ValueError('invalid Cancel bounds')
    x1,y1,x2,y2=map(int,match.groups())
    if not (0<=x1<x2<=8192 and 0<=y1<y2<=8192):
        raise ValueError('unsafe Cancel bounds')
    return (x1+x2)//2,(y1+y2)//2

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--hierarchy',type=Path,required=True)
    p.add_argument('--action',required=True,choices=['verify','cancel-coordinates'])
    a=p.parse_args()
    try:
        xy=parse(a.hierarchy)
    except (OSError,ValueError,ET.ParseError) as e:
        print('BH_APP01_P07_HF02_REFUSED: '+str(e),file=sys.stderr)
        return 12
    if a.action=='cancel-coordinates':print(*xy)
    else:print('BH_APP01_P07_HF02_QS_UI_CONFIRM_PASS')
    return 0
if __name__=='__main__':sys.exit(main())
