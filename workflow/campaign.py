#!/usr/bin/env python3
"""Independent farm orchestration. Never releases/removes existing jobs."""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import uuid

from core import certificates, checked_audits, charge_table, decode, multiplicities
from mb_config import build_mb_options, checked_mb_stdout

from io_utils import load, now, save, sha
from runtime import HERE, BASE, PILOT, PROD, generator_environment

V5_BINARY = 'e509ba6eae8ac43b3ac085ea4c52d6a98de2cd2867d13c5976eb3964bc1c2ac7'
CERTIFIED_REUSED_V4_BINARY = '757fc0cb266986fe1bf5ecc3a3934b7c51b8907dd1b7a55accf523b0e625c5a4'


def signature_of(p):
    payload={k:p[k] for k in ('records','code_sha','mb_jobs','templates','source_jobs','bootstrap')}
    if 'source_reuse' in p:payload['source_reuse']=p['source_reuse']
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def physics(text):
    lines=[]
    for line in text.splitlines():
        line=line.split('!',1)[0].strip()
        if not line or re.match(r'set\s+(nfull|seedj|seedi|modsho)\s',line):continue
        lines.append(' '.join(line.split()))
    return '\n'.join(lines)


def completed_production(base,system):
    """Read existing completion evidence; supports old and portable batches."""
    base=Path(base);records=[];template=None
    config=load(base/'_batch/batch_config.json')
    assert config.get('system',system)==system,'production system mismatch'
    for marker in sorted((base/'done').glob('*.json')):
        m=load(marker)
        if m.get('status')!='PASS':continue
        work=base/'jobs'/('cluster_'+str(m['cluster']))/('job_%05d'%m['process'])
        assert load(work/'SHARD_COMPLETE.json')==m,'published completion disagreement'
        assert sha(work/'RESULT_SHA256SUMS')==m['result_manifest_sha256']
        records.append(dict(system=system,work=str(work),root=m['root'],log=str(work/'generator.stdout'),
                            seedj=m['seedj'],seedi=m['seedi'],expected=m['retained_events'],
                            expected_sha=m['root_sha256'],binary=m['binary_sha256'],hq=m['hq_sha256'],
                            mode='generator_v5_production',marker=str(marker),marker_sha=sha(marker)))
        template=dict(work=str(work),source=str(config.get('source',base/'_batch/runtime/source')),
                      install=str(config.get('install',base/'_batch/runtime/install')))
    return records,template


def prepare():
    import uproot
    assert not (HERE/'PLAN.json').exists(),'already frozen; inspect existing plan'
    records=[];excluded=[];templates={};seen=set();compatible={}
    for system in ('PbPb','OO'):
        for marker in sorted((PILOT/'jobs'/system).glob('*/SHARD_COMPLETE.json')):
            done=load(marker);work=marker.parent;m=load(work/'PRODUCED.json')
            assert done['repair_mode'] in ('generator_v5','reused_v4_no_overflow')
            roots=list((work/'check').glob('*.root'))
            if len(roots)!=1:raise ValueError('ambiguous/missing pilot ROOT: '+str(work))
            records.append(dict(system=system,work=str(work),root=str(roots[0]),log=str(work/'generator.stdout'),
                                seedj=m['seedj'],seedi=m['seedi'],expected=m['retained_events'],
                                expected_sha=m['root_sha256'],binary=m['binary_sha256'],hq=m['hq_sha256'],
                                mode=done['repair_mode'],marker=str(marker),marker_sha=sha(marker)))
            if system not in templates and done['repair_mode']=='generator_v5':
                templates[system]=dict(work=str(work),source=str(PILOT/'full_source'),install=str(PILOT/'install'))
    additions,template=completed_production(PROD,'OO');records.extend(additions)
    if template is not None:templates['OO']=template
    if os.environ.get('EPOS_PBPB_PRODUCTION'):
        additions,template=completed_production(os.environ['EPOS_PBPB_PRODUCTION'],'PbPb');records.extend(additions)
        if template is not None:templates['PbPb']=template
    assert records and set(templates)=={'PbPb','OO'}
    (HERE/'templates').mkdir(exist_ok=True)
    for system,t in templates.items():
        work=Path(t['work'])
        shutil.copy2(str(work/'pilot.clinput'),str(HERE/'templates'/(system+'.clinput')))
        shutil.copy2(str(work/'pilot.optns'),str(HERE/'templates'/(system+'.optns')))
        t['original_work']=str(work)
    accepted=[];root_hashes=set()
    for i,r in enumerate(records):
        key=(r['system'],r['seedj'],r['seedi'])
        if key in seen:
            excluded.append(dict(root=r['root'],reason='duplicate simulation seed'));continue
        seen.add(key);p=Path(r['root']);before=p.stat()
        opt=(Path(r['work'])/'pilot.optns').read_text();sig=hashlib.sha256(physics(opt).encode()).hexdigest()
        expected_build=CERTIFIED_REUSED_V4_BINARY if r['mode']=='reused_v4_no_overflow' else V5_BINARY
        assert r['binary']==expected_build,'unapproved build version'
        prior=compatible.setdefault(r['system'],(r['hq'],sig))
        assert prior==(r['hq'],sig),'incompatible physics settings in '+r['root']
        digest=sha(p)
        assert digest==r['expected_sha'],'source ROOT checksum mismatch: '+str(p)
        assert digest not in root_hashes,'duplicate ROOT content';root_hashes.add(digest)
        after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        r.update(index=len(accepted),root_sha=digest,bytes=after.st_size,mtime_ns=after.st_mtime_ns,
                 log_sha=sha(r['log']),physics_signature=sig)
        accepted.append(r)
        if i%50==0:print('FROZEN_SOURCE',i,'of',len(records),flush=True)
    for system,t in templates.items():
        assert sha(Path(t['install'])/'bin/Xepos')==V5_BINARY
        assert sha(Path(t['source'])/'srcext/HQ/hq.i')==compatible[system][0]
    table=Path(templates['OO']['source'])/'src/KWt/idt.dt'
    shutil.copy2(str(table),str(HERE/'idt.dt'))
    assert sha(Path(templates['PbPb']['source'])/'src/KWt/idt.dt')==sha(HERE/'idt.dt')
    shutil.copy2(str(PILOT/'SOURCE_SCOPE_AUDIT.json'),str(HERE/'SOURCE_SCOPE_AUDIT.json'))
    jobs=[]
    for system in ('PbPb','OO'):
        rows=[r['index'] for r in accepted if r['system']==system]
        for start in range(0,len(rows),25):jobs.append(dict(key=system+'_%03d'%(start//25),indices=rows[start:start+25]))
    mb=[]
    for si,system in enumerate(('PbPb','OO')):
        for j in range(200):
            seed=910000001+si*10000000+j*7919
            assert (system,seed,222222222) not in seen
            mb.append(dict(key=system+'_%03d'%j,system=system,events=100,seedj=seed,seedi=222222222,
                           split='calibration' if j<150 else 'validation'))
    files={p.name:sha(p) for p in HERE.glob('*.py')}
    files.update({'idt.dt':sha(HERE/'idt.dt'),'SOURCE_SCOPE_AUDIT.json':sha(HERE/'SOURCE_SCOPE_AUDIT.json')})
    files.update({str(t.relative_to(HERE)):sha(t) for t in (HERE/'templates').glob('*')})
    signature=hashlib.sha256(json.dumps(dict(records=accepted,files=files,mb=mb),sort_keys=True).encode()).hexdigest()
    save(HERE/'PLAN.json',dict(version=1,utc=now(),signature=signature,records=accepted,excluded=excluded,
                             source_jobs=jobs,mb_jobs=mb,templates=templates,code_sha=files,
                             bootstrap=1000,old_jobs_must_remain_held=True))
    write_submit(jobs,mb)
    print('PLAN_FROZEN',signature,'source_files',len(accepted),flush=True)


def frozen():
    p=load(HERE/'PLAN.json')
    assert signature_of(p)==p['signature'],'changed scientific plan or execution partition'
    for n,h in p['code_sha'].items():assert sha(HERE/n)==h,'changed frozen source: '+n
    runtime=load(HERE/'PYTHON_RUNTIME.json')
    for n,h in runtime['external_files'].items():assert sha(n)==h,'changed shared Python runtime: '+n
    if p.get('input_freeze_sha256'):
        assert sha(HERE/'PLAN.input_freeze.json')==p['input_freeze_sha256']
    return p


def seal():
    """Complete the execution-file seal BEFORE preflight or any submission.

    Retain the initial input freeze, including its original signature. This
    does not rescan or change scientific inputs and is forbidden after submit.
    """
    assert not (HERE/'SUBMITTED.json').exists() and not (HERE/'.submit.lock').exists()
    assert not (HERE/'PREFLIGHT_PASS.json').exists(),'preflight already bound; never silently reseal'
    p=load(HERE/'PLAN.json');backup=HERE/'PLAN.input_freeze.json'
    assert not backup.exists(),'already sealed'
    save(backup,p)
    files=list(HERE.glob('*.py'))+list(HERE.glob('*.sub'))+list(HERE.glob('*.items'))
    files+=[HERE/n for n in ['launch.sh','requirements-farm.txt','analysis.dag','idt.dt','SOURCE_SCOPE_AUDIT.json',
                            'PYTHON_RUNTIME.json','VENDOR_MANIFEST.json','RUNTIME_SMOKE_PASS.json']]
    if (HERE/'site.env').exists():files.append(HERE/'site.env')
    if p.get('source_reuse'):files.append(HERE/'REUSE_SOURCE_CACHE.json')
    files+=list((HERE/'templates').glob('*'))
    p['code_sha']={str(f.relative_to(HERE)):sha(f) for f in files}
    p['input_freeze_signature']=p['signature'];p['input_freeze_sha256']=sha(backup)
    p['signature']=signature_of(p)
    p['sealed_utc']=now();save(HERE/'PLAN.json',p)
    print('EXECUTION_SEALED',p['signature'],flush=True)


def output_events(root_path,record,charge,mb=False):
    import uproot
    text='' if mb else Path(record['log']).read_text()
    cert={} if mb else certificates(text)
    evidence={} if mb else checked_audits(text,record['expected'])
    audit=collections.Counter();seen=set()
    audit['generator_event_audits']=len(evidence)
    audit['generator_truncated_tag_records']=sum(v.get('truncated_known',0) for v in evidence.values())
    f=uproot.open(str(root_path));t=f['teposevent0'] if 'teposevent0' in f else f['teposevent']
    assert t.num_entries==record['expected'],'ROOT event count mismatch'
    names=['id','ist','ity','px','py','pz','e','bim','phi','phir']
    if not mb:names+=['fdEvent','fdLineageVersion','fdPair','fdTrack','fdLeg','fdOrigin','fdReason']
    assert set(names).issubset(t.keys())
    for entry in range(t.num_entries):
        ar=t.arrays(names,entry_start=entry,entry_stop=entry+1,library='np');v={k:ar[k][0] for k in names}
        ev=entry+1 if mb else int(v['fdEvent'])
        assert ev>0 and ev not in seen;seen.add(ev)
        assert mb or ev in evidence,'ROOT event has no matching lineage audit'
        assert mb or int(v['fdLineageVersion']) in (4,5)
        key=record['system']+'/'+str(record['seedj'])+'/'+str(record['seedi'])+'/'+str(ev)
        event_audit=collections.Counter()
        pairs,all_final=([],[]) if mb else decode(v,ev,cert,event_audit)
        audit.update(event_audit)
        yield dict(key=key,file_index=record.get('index',-1),entry=entry,event=ev,system=record['system'],
                   m=multiplicities(v,charge),b=float(v['bim']),ep=float(v['phi'])+float(v['phir']),
                   pairs=pairs,final_D0=all_final,audit=dict(event_audit))
    record['audit']=dict(audit)


def extract_locked(key):
    p=frozen();job=next(j for j in p['source_jobs'] if j['key']==key)
    out=HERE/'extracted'/key;out.mkdir(parents=True,exist_ok=True)
    charge=charge_table(HERE/'idt.dt')
    for index in job['indices']:
        r=dict(p['records'][index]);target=out/('%06d.jsonl.gz'%index);done=target.with_suffix('.COMPLETE.json')
        if done.exists():
            m=load(done);assert m['signature']==p['signature'] and sha(target)==m['sha256'];continue
        st=Path(r['root']).stat();assert (st.st_size,st.st_mtime_ns)==(r['bytes'],r['mtime_ns'])
        assert sha(r['log'])==r['log_sha']
        tmp=target.with_name(target.name+'.tmp.'+str(os.getpid()));count=0
        with gzip.open(str(tmp),'wt') as f:
            for event in output_events(r['root'],r,charge):
                f.write(json.dumps(event,allow_nan=False,separators=(',',':'))+'\n');count+=1
        os.replace(str(tmp),str(target))
        save(done,dict(signature=p['signature'],events=count,sha256=sha(target),audit=r.get('audit',{}),utc=now()))
        print('SOURCE_EXTRACT_PASS',index,count,flush=True)


def extract(key):
    out=HERE/'extracted'/key;out.mkdir(parents=True,exist_ok=True)
    lock=out/'.lock';lock.mkdir()
    save(lock/'owner.json',dict(host=socket.gethostname(),pid=os.getpid(),utc=now()))
    try:extract_locked(key)
    finally:
        (lock/'owner.json').unlink();lock.rmdir()


def mb_worker(key,pilot=False):
    p=frozen()
    if pilot:
        system=key;job=dict(key=system,system=system,events=2,seedj=930000001+(system=='OO')*10000000,
                          seedi=222222222,split='pilot')
    else:job=next(j for j in p['mb_jobs'] if j['key']==key);system=job['system']
    parent=HERE/('mb_pilot' if pilot else 'mb')/key;parent.mkdir(parents=True,exist_ok=True)
    done=parent/'COMPLETE.json'
    if done.exists():
        m=load(done);assert m['signature']==p['signature'] and sha(parent/'events.jsonl.gz')==m['events_sha'];return
    lock=parent/'.lock';lock.mkdir()
    try:
        work=parent/('attempt_'+uuid.uuid4().hex);work.mkdir();(work/'check').mkdir();(work/'histo').mkdir()
        t=p['templates'][system];source=Path(t['source']);install=Path(t['install'])
        assert sha(install/'bin/Xepos')==V5_BINARY
        assert sha(source/'srcext/HQ/hq.i')==next(r['hq'] for r in p['records'] if r['system']==system)
        assert sha(source/'src/KWt/idt.dt')==sha(HERE/'idt.dt'),'generator charge table changed'
        opt=build_mb_options((HERE/'templates'/(system+'.optns')).read_text(),job['events'],job['seedj'],job['seedi'])
        (work/'pilot.optns').write_text(opt)
        cl=(HERE/'templates'/(system+'.clinput')).read_text().replace(t['original_work'],str(work))
        cl=re.sub(r'set seedj\s+\d+', 'set seedj '+str(job['seedj']),cl)
        cl=re.sub(r'set seedi\s+\d+', 'set seedi '+str(job['seedi']),cl)
        (work/'pilot.clinput').write_text(cl)
        with gzip.open(str(source/'src/KWt/eos4f.eos.gz'),'rb') as a,(work/'z-eos4f.eos').open('wb') as b:shutil.copyfileobj(a,b)
        env=generator_environment(t,work)
        libraries=subprocess.check_output(['/usr/bin/ldd',str(install/'bin/Xepos')],env=env,universal_newlines=True)
        assert 'not found' not in libraries,'missing execution-host generator library'
        save(work/'STARTED.json',dict(job=job,host=socket.gethostname(),utc=now(),signature=p['signature']))
        with (work/'generator.stdout').open('wb') as stdout,(work/'generator.stderr').open('wb') as stderr:
            result=subprocess.run([str(install/'bin/Xepos'),'-n'],input=b'pilot.clinput\n',cwd=str(work),env=env,stdout=stdout,stderr=stderr)
        assert result.returncode==0,'MB generator failed; attempt preserved'
        text=(work/'generator.stdout').read_text()
        evidence=checked_mb_stdout(text)
        roots=list((work/'check').glob('*.root'));assert len(roots)==1
        import uproot
        with uproot.open(str(roots[0])) as f:
            tree=f['teposevent0'] if 'teposevent0' in f else f['teposevent']
            evidence['root_events']=tree.num_entries
            assert tree.num_entries==job['events'],'incomplete MB event retention'
            no_charm=0
            for arrays in tree.iterate(['id','ist'],step_size='20 MB',library='np'):
                no_charm+=sum(not any(abs(int(i))==4 and int(s)==21 for i,s in zip(ids,states))
                              for ids,states in zip(arrays['id'],arrays['ist']))
            evidence['events_without_initial_charm']=no_charm
        rec=dict(system=system,seedj=job['seedj'],seedi=job['seedi'],expected=job['events'])
        target=parent/'events.jsonl.gz';temp=parent/'events.tmp.jsonl.gz'
        with gzip.open(str(temp),'wt') as f:
            for event in output_events(roots[0],rec,charge_table(HERE/'idt.dt'),mb=True):
                event['split']=job['split'];f.write(json.dumps(event,separators=(',',':'),allow_nan=False)+'\n')
        os.replace(str(temp),str(target))
        save(done,dict(signature=p['signature'],job=job,root=str(roots[0]),root_sha=sha(roots[0]),
                       events_sha=sha(target),stdout_sha=sha(work/'generator.stdout'),evidence=evidence,utc=now()))
        print('MB_PASS',key,job['events'],flush=True)
    finally:lock.rmdir()


def check_pilot():
    p=frozen()
    for s in ('PbPb','OO'):
        m=load(HERE/'mb_pilot'/s/'COMPLETE.json')
        assert m['signature']==p['signature'] and m['job']['events']==2
        assert m['evidence']['runtime_iskip'] and set(m['evidence']['runtime_iskip'])=={0}
        assert m['evidence']['root_events']==2 and m['evidence']['skipped_no_charm']==0
        if s=='OO':assert m['evidence']['events_without_initial_charm']>0,'known no-charm OO test must retain a no-charm event'
    save(HERE/'MB_PILOT_PASS.json',dict(signature=p['signature'],utc=now(),status='PASS'))


def write_submit(jobs,mb):
    (HERE/'logs').mkdir(exist_ok=True)
    def sub(name,args,queue):
        (HERE/(name+'.sub')).write_text('universe = vanilla\nexecutable = '+str(HERE/'launch.sh')+'\narguments = '+args+'\ninitialdir = '+str(HERE)+'\noutput = '+str(HERE/'logs')+'/'+name+'_$(Cluster)_$(Process).out\nerror = '+str(HERE/'logs')+'/'+name+'_$(Cluster)_$(Process).err\nlog = '+str(HERE/'logs/condor.log')+'\n'+queue+'\n')
    sub('runtime_smoke','runtime-smoke','queue 1')
    sub('pilot','mb-pilot $(System)','queue System in PbPb,OO')
    sub('check_pilot','check-pilot','queue 1')
    (HERE/'source.items').write_text(''.join(j['key']+'\n' for j in jobs))
    (HERE/'mb.items').write_text(''.join(j['key']+'\n' for j in mb))
    if (HERE/'REUSE_SOURCE_CACHE.json').exists():sub('sources','verify-reuse','queue 1')
    else:sub('sources','extract $(Key)','queue Key from '+str(HERE/'source.items'))
    sub('mb','mb $(Key)','queue Key from '+str(HERE/'mb.items'))
    sub('calibration','calibrate','queue 1');sub('analysis','analyze','queue 1')
    (HERE/'analysis.dag').write_text('JOB PILOT pilot.sub\nJOB CHECK check_pilot.sub\nJOB SOURCES sources.sub\nJOB MB mb.sub\nJOB CALIBRATION calibration.sub\nJOB ANALYSIS analysis.sub\nPARENT PILOT CHILD CHECK\nPARENT CHECK CHILD MB\nPARENT MB CHILD CALIBRATION\nPARENT SOURCES CALIBRATION CHILD ANALYSIS\n')


def submit():
    p=frozen();proof=load(HERE/'PREFLIGHT_PASS.json')
    assert proof['signature']==p['signature'] and proof['status']=='PASS'
    lock=HERE/'.submit.lock';lock.mkdir()
    save(lock/'attempt.json',dict(utc=now(),signature=p['signature']))
    r=subprocess.run(['condor_submit_dag','-notification','Never','-priority','2147483647','analysis.dag'],cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
    save(HERE/'SUBMITTED.json',dict(utc=now(),returncode=r.returncode,stdout=r.stdout,signature=p['signature']))
    assert r.returncode==0,r.stdout
    print(r.stdout)


if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='prepare':prepare()
    elif cmd=='seal':seal()
    elif cmd=='extract':extract(sys.argv[2])
    elif cmd=='mb':mb_worker(sys.argv[2])
    elif cmd=='mb-pilot':mb_worker(sys.argv[2],True)
    elif cmd=='check-pilot':check_pilot()
    elif cmd=='prepare-reuse':
        from reuse_cache import prepare_reuse
        prepare_reuse()
    elif cmd=='verify-reuse':
        from reuse_cache import verify_reuse
        verify_reuse(frozen())
    elif cmd=='submit':submit()
    elif cmd in ('calibrate','analyze'):
        import analysis
        getattr(analysis,cmd)()
    else:raise ValueError('unknown command')

