#!/bin/bash
set -euo pipefail
export LC_ALL=C LANG=C PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
# Numerical libraries must not create one thread per core on a shared host.
# These are execution settings, not scheduler resource/node requests.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /storage/fdunphome/enrich/EPOS4HQ/initial_source_memory_20261116_r4
export PYTHONHOME=/storage/fdunphome/enrich/EPOS4HQ/ccbar_lineage_pilot_20260921/runtime_python36_20260928
export PYTHONPATH="$PWD/vendor"
export LD_LIBRARY_PATH="$PYTHONHOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ "${1:-}" == runtime-smoke ]]; then
  exec "$PYTHONHOME/bin/python3.6" runtime_smoke.py
fi
exec "$PYTHONHOME/bin/python3.6" campaign.py "$@"
