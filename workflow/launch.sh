#!/bin/bash
set -euo pipefail
export LC_ALL=C LANG=C PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
# Numerical-library threads, not HTCondor resource/node restrictions.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$(dirname "$0")"
if [[ -f ./site.env ]]; then source ./site.env; fi
base="${EPOS_BASE:-$HOME/EPOS4HQ}"
export PYTHONHOME="${EPOS_PYTHONHOME:-$base/ccbar_lineage_pilot_20260921/runtime_python36_20260928}"
export PYTHONPATH="$PWD/vendor"
export LD_LIBRARY_PATH="$PYTHONHOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python="$PYTHONHOME/bin/python3.6"
if [[ "${1:-}" == runtime-smoke ]]; then
  exec "$python" runtime_smoke.py
fi
if [[ "${1:-}" == prepare-runtime ]]; then
  exec "$python" prepare_runtime.py
fi
if [[ "${1:-}" == preflight ]]; then
  exec "$python" preflight.py
fi
exec "$python" campaign.py "$@"
