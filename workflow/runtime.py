"""Portable paths. Set EPOS_BASE; keep simulation binaries outside Git."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get("EPOS_BASE", str(Path.home() / "EPOS4HQ"))).resolve()
PILOT = Path(os.environ.get("EPOS_TAGGED_SOURCE", str(BASE / "ccbar_lineage_pilot_20260921/large_v5repair_20261009_005500")))
PROD = Path(os.environ.get("EPOS_OO_PRODUCTION", str(BASE / "OO/output_1021")))


def generator_environment(template,work,base_env=None):
    """Do not depend on a submit-host login shell's LD_LIBRARY_PATH."""
    env=dict(os.environ if base_env is None else base_env)
    root=BASE/'root/root';source=Path(template['source']);install=Path(template['install'])
    libs=[str(root/'lib'),str(BASE/'HepMC3/install/lib64'),str(BASE/'fastjet/fastjet-install/lib')]
    env['LD_LIBRARY_PATH']=':'.join(libs+([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
    env['PATH']=str(root/'bin')+':'+env.get('PATH','/usr/bin:/bin')
    env.update(ROOTSYS=str(root),EPO=str(source)+'/',DAT=str(install/'share')+'/',OPT=str(work)+'/',
               HTO=str(work/'histo')+'/',CHK=str(work/'check')+'/',LC_ALL='C',LANG='C')
    for k in ('seedj','seedc','seedi'):env.pop(k,None)
    return env
