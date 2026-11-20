"""OO v5 production: one attempt per scheduler job; never overwrite outputs."""
import datetime,gzip,hashlib,json,os,pathlib,re,shutil,subprocess,sys,traceback
from lineage_records import parse

HERE=pathlib.Path(__file__).resolve().parent
OUT=HERE.parent
ROOT='/storage/fdunphome/enrich/EPOS4HQ/root/root/bin/root'
def sha(path):
    h=hashlib.sha256()
    with open(str(path),'rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest()
def save(path,value):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(str(temp),str(path))
def run(cluster,index):
    config=json.loads((HERE/'batch_config.json').read_text())
    assert cluster.isdigit() and index.isdigit()
    cluster,index=int(cluster),int(index)
    assert 0<=index<config['jobs']
    events=config['events_per_job'];seed=config['seed_base']+config['seed_stride']*index
    assert events==100 and 0<seed<1000000000
    work=OUT/'jobs'/('cluster_'+str(cluster))/('job_%05d'%index)
    assert not work.exists(),'Existing attempt: preserve it; do not auto-rerun'
    work.mkdir(parents=True,exist_ok=False)
    os.chdir(str(work))
    for n in ('check','histo'):(work/n).mkdir()
    install=HERE/'runtime/install';source=HERE/'runtime/source'
    assert sha(install/'bin/Xepos')==config['binary_sha256']
    assert sha(source/'srcext/HQ/hq.i')==config['hq_sha256']
    opts=(HERE/'OO_100events_v5.optns').read_text()
    opts+='\n! independent production seed; physical settings unchanged\nset seedj %d\nset seedi %d\n'%(seed,config['seedi'])
    (work/'pilot.optns').write_text(opts)
    env=os.environ.copy()
    env.update(EPO=str(source)+'/',DAT=str(install/'share')+'/',OPT=str(work)+'/',HTO=str(work/'histo')+'/',CHK=str(work/'check')+'/')
    for k in ('seedj','seedc','seedi'):env.pop(k,None)
    src=install/'share/src';ext=install/'share/srcext';conf=install/'share/config'
    lines=['set seedj %d set seedi %d'%(seed,config['seedi']),'echo off','rootcproot yesno','system i','ext1 -','ext3 -','ext4 -','set gefac 1','fname pathep '+str(source)+'/',
           'fname user1 '+str(ext/'HQt')+'/','fname user2 '+str(work/'histo/pilot.hq'),'fname user3 '+str(ext/'URt')+'/','fname pathpdf '+str(src/'TPt')+'/']
    for name,suffix in [('histo','histo/pilot.histo'),('check','check/pilot.check'),('copy','check/pilot.copy'),('log','check/pilot.log'),('data','check/pilot.data')]:lines.append('fname '+name+' '+str(work/suffix))
    for name,p in [('initl',src/'KWt/aa.i'),('inidi',src/'TPt/di.i'),('inidr',src/'KWt/dr.i'),('iniev',src/'KWt/ev.i'),('inirj',src/'KWt/rj.i'),('inics',src/'TPt/cs.i'),('inigrv',src/'grv.i'),('partab',ext/'YK/ptl6.data'),('dectab',ext/'YK/dky6.data'),('hpf',ext/'UR/tables.dat')]:lines.append('fname '+name+' '+str(p))
    for i in [1220,-1220,120,130,-20,14,-14,16,-16]:lines.append('nodecay '+str(i))
    lines+=['echo on','input '+str(conf/'parbf.i'),'input '+str(work/'pilot.optns'),'input '+str(src/'KWn/paraf.i'),'input '+str(conf/'partx.i'),'runprogram','stopprogram']
    (work/'pilot.clinput').write_text('\n'.join(lines)+'\n')
    eos=work/'z-eos4f.eos'
    with gzip.open(str(src/'KWt/eos4f.eos.gz'),'rb') as a,eos.open('wb') as b:shutil.copyfileobj(a,b)
    manifest=dict(run_id=config['run_id'],system='OO',cluster=cluster,process=index,requested_events=events,seedj=seed,seedi=config['seedi'],host=os.uname().nodename,start_utc=datetime.datetime.utcnow().isoformat()+'Z',binary_sha256=config['binary_sha256'],optns_sha256=sha(work/'pilot.optns'),hq_sha256=config['hq_sha256'],frozen_manifest_sha256=sha(HERE/'FROZEN_SHA256SUMS'))
    save(work/'STARTED.json',manifest)
    print('SIMULATION_START '+json.dumps(manifest,sort_keys=True),flush=True)
    with (work/'generator.stdout').open('wb') as out,(work/'generator.stderr').open('wb') as err:
        result=subprocess.run([str(install/'bin/Xepos'),'-n'],input=b'pilot.clinput\n',env=env,stdout=out,stderr=err)
    assert result.returncode==0,'generator exit '+str(result.returncode)
    text=(work/'generator.stdout').read_text(errors='strict')
    skipped=len(re.findall(r'(?m)^\s*No c quarks, event skipped\s*$',text))
    generated=re.findall(r'generate\s+(\d+)\s+events for engy',text)
    stored=list(map(int,re.findall(r'(?m)^nrevt:\s*(\d+)\s+seedj:',text)))
    assert generated==[str(events)] and re.search(r'(?m)^stop program;',text),'abnormal generator completion'
    assert 0<=skipped<=events and stored==list(range(1,events-skipped+1)),'event accounting'
    audits,sources=parse(text,events-skipped)
    save(work/'LINEAGE_AUDIT.json',audits);save(work/'SOURCE_CERTIFICATES.json',sources)
    manifest.update(skipped_no_charm=skipped,retained_events=events-skipped,source_certificate_count=len(sources))
    save(work/'EVENT_ACCOUNTING.json',manifest)
    root=work/'check/pilot.root'
    expr=str(HERE/'ValidateOO.C')+'("'+str(root)+'","'+str(work/'generator.stdout')+'","'+str(work/'ROOT_VALIDATION.json')+'",'+str(events)+','+str(skipped)+',5)'
    with (work/'validation.log').open('wb') as out:subprocess.run([ROOT,'-l','-b','-q',expr],env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    valid=json.loads((work/'ROOT_VALIDATION.json').read_text())
    assert valid['status']=='PASS' and valid['errors']==0
    assert sorted(valid['event_ids'])==sorted(a['event'] for a in audits),'event identity mismatch'
    final=None
    if root.is_file():
        digest=sha(root)
        final=OUT/'check/OO'/('z-OO_100events_v5-%d-%05d.root'%(cluster,index))
        os.link(str(root),str(final))
        root.unlink()
        manifest.update(root=str(final),root_sha256=digest,root_bytes=final.stat().st_size)
    else:assert events==skipped
    # Only remove a decompressed copy of a bundled input table, never simulation products.
    eos.unlink()
    manifest['end_utc']=datetime.datetime.utcnow().isoformat()+'Z'
    save(work/'PRODUCED.json',manifest)
    products=[work/n for n in ('STARTED.json','EVENT_ACCOUNTING.json','LINEAGE_AUDIT.json','SOURCE_CERTIFICATES.json','ROOT_VALIDATION.json','PRODUCED.json','pilot.optns','pilot.clinput','generator.stdout','generator.stderr','validation.log')]
    if final:products.append(final)
    checksums=work/'RESULT_SHA256SUMS'
    with checksums.open('x') as f:
        for p in products:f.write(sha(p)+'  '+str(p)+'\n')
    marker=dict(manifest,status='PASS',result_manifest_sha256=sha(checksums))
    save(work/'SHARD_COMPLETE.json',marker)
    save(OUT/'done'/('job-%d-%05d.json'%(cluster,index)),marker)
    print('OO_V5_JOB_PASS cluster=%d process=%d requested=%d retained=%d'%(cluster,index,events,events-skipped),flush=True)
if __name__=='__main__':
    try:
        assert len(sys.argv)==3,'cluster and process required'
        run(sys.argv[1],sys.argv[2])
    except BaseException:
        print('OO_V5_JOB_FAIL; all products preserved; no automatic retry',file=sys.stderr)
        traceback.print_exc();sys.exit(90)
