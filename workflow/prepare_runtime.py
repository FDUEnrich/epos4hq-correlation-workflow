"""Stage dependencies without installing/changing any worker-node software."""
import os
import shutil
import subprocess
from pathlib import Path
from campaign import HERE, BASE, load, save, sha, now


def main():
    runtime=Path(os.environ.get('EPOS_PYTHONHOME',str(BASE/'ccbar_lineage_pilot_20260921/runtime_python36_20260928')))
    subprocess.check_output(['sha256sum','-c','SHA256SUMS'],cwd=str(runtime),stderr=subprocess.STDOUT)
    target=HERE/'vendor'
    assert not target.exists(),'never overwrite vendored dependencies'
    source=Path(os.environ.get('EPOS_VENDOR_SOURCE',str(BASE/'initial_source_memory_20261115/venv/lib/python3.6/site-packages')))
    shutil.copytree(str(source),str(target),ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    manifest={str(f.relative_to(target)):sha(f) for f in target.rglob('*') if f.is_file()}
    save(HERE/'VENDOR_MANIFEST.json',manifest)
    files=[runtime/n for n in ['bin/python3.6','lib64/libpython3.6m.so.1.0','SHA256SUMS','PROVENANCE.json']]
    save(HERE/'PYTHON_RUNTIME.json',dict(utc=now(),prefix=str(runtime),external_files={str(f):sha(f) for f in files},
                                      vendor_origin=str(source),vendor_manifest=sha(HERE/'VENDOR_MANIFEST.json')))
    print('SHARED_RUNTIME_STAGED',len(manifest),flush=True)


if __name__=='__main__':main()
