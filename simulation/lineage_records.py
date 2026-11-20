"""Strict field schemas, independent of mixed Fortran/C++ line prefixes."""
import re

AUDIT_FIELDS=('event born timelike spacelike unresolved_eol_charm sl_mismatch '
 'ptl_charm ptl_known hq_in_moves hq_particle_moves hq_out_moves urqmd_moves '
 'root_moves single_root_imports shower_shape_errors sea_sources sea_imports '
 'sea_mismatch carrier_errors truncated_known').split()
SOURCE_FIELDS='event pair origin side a b parent first second'.split()
MANDATORY=('sl_mismatch','shower_shape_errors','sea_mismatch','carrier_errors')

def records(text,kind,fields):
    token=kind+' '
    pattern=re.compile(re.escape(token)+' '.join(re.escape(k)+r'=(-?\d+)' for k in fields)+r'(?=\s|$)')
    starts=[m.start() for m in re.finditer(re.escape(token),text)]
    found=list(pattern.finditer(text))
    if starts!=[m.start() for m in found]:
        raise ValueError('Truncated or malformed '+kind+' record')
    return [dict(zip(fields,map(int,m.groups()))) for m in found]

def parse(text,retained):
    audits=records(text,'FD_AUDIT',AUDIT_FIELDS)
    sources=records(text,'FD_SOURCE',SOURCE_FIELDS)
    ids=[a['event'] for a in audits]
    if len(audits)!=retained or len(set(ids))!=len(ids) or any(e<=0 for e in ids):
        raise ValueError('FD_AUDIT event identities/count mismatch')
    if any(a[k]!=0 for a in audits for k in MANDATORY):
        raise ValueError('Nonzero mandatory lineage audit')
    keys=[(s['event'],s['pair']) for s in sources]
    if len(keys)!=len(set(keys)) or any(e<=0 or p<=0 for e,p in keys):
        raise ValueError('Duplicate/nonpositive FD_SOURCE identity')
    return audits,sources

def selftest():
    a='FD_AUDIT '+' '.join(k+'='+('1' if k=='event' else '0') for k in AUDIT_FIELDS)
    s='FD_SOURCE event=1 pair=1 origin=1 side=0 a=0 b=0 parent=0 first=4 second=-4'
    for prefix in ('','checkengy ','destroy emuc; memory 6723'):
        aa,ss=parse(prefix+a+'\n'+prefix+s+'\n',1)
        assert aa[0]['event']==1 and ss[0]['second']==-4
    for bad in (a.replace('sea_mismatch=0','sea_mismatch=1'),a[:-1],a+'\n'+a,a.replace('event=1','event=0')):
        try:parse(bad+'\n'+s,1)
        except ValueError:pass
        else:raise AssertionError('accepted invalid audit')
    for bad in (s[:-1],s+'\n'+s):
        try:parse(a+'\n'+bad,1)
        except ValueError:pass
        else:raise AssertionError('accepted invalid certificate')
    assert parse('',0)==([],[])
    print('LINEAGE_RECORDS_TEST_PASS prefixes, truncation, duplicate, nonzero, empty')

if __name__=='__main__':selftest()
