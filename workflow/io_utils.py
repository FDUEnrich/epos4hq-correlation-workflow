"""Small shared I/O helpers; scientific payload formats are unchanged."""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path


def now():return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()+'Z'


def sha(path):
    h=hashlib.sha256()
    with open(str(path),'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp.'+str(os.getpid()))
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    os.replace(str(tmp),str(path))


def load(path):return json.loads(Path(path).read_text())


def read_events(path):
    with gzip.open(str(path),'rt') as f:
        for line in f:yield json.loads(line)

