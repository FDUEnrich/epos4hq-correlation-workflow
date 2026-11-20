#!/bin/bash
set -euo pipefail
export LC_ALL=C LANG=C
here=/storage/fdunphome/enrich/EPOS4HQ/OO/output_1021/_batch
export ROOTSYS=/storage/fdunphome/enrich/EPOS4HQ/root/root
export PYTHONHOME="$here/runtime/python36"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
export PATH="$ROOTSYS/bin:/usr/bin:/bin"
export LD_LIBRARY_PATH="$PYTHONHOME/lib64:$ROOTSYS/lib:/storage/fdunphome/enrich/EPOS4HQ/HepMC3/install/lib64:/storage/fdunphome/enrich/EPOS4HQ/fastjet/fastjet-install/lib"
cd "$here"
sha256sum --quiet -c FROZEN_SHA256SUMS
if [[ $# == 1 && "$1" == --preflight ]]; then
  exec "$PYTHONHOME/bin/python3.6" -S -B "$here/preflight.py"
fi
exec "$PYTHONHOME/bin/python3.6" -S -B "$here/worker.py" "$@"
