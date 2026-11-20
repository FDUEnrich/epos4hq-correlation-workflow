"""One RNG pass, shared across spectra, migrations and angular memory.

The draws and their ordering are identical to r4's draw-and-replay loops.
"""
import numpy as np
from centrality import masks, reference_percentiles


def joint_bootstrap(eids, bins, values, size, multiplicity, keys, frequency,
                    system, estimator_index, replicas=1000, progress=True):
    n = len(keys)
    reps = np.zeros((replicas, 4, size))
    totals = np.zeros((replicas, 4))
    groups = np.zeros((replicas, n), dtype=np.uint8)
    draws = np.empty((replicas, n), dtype=np.int32)
    rng = np.random.RandomState(15112026 + (system == 'OO') * 97 + estimator_index * 13)
    for boot in range(replicas):
        draw = rng.multinomial(n, np.ones(n) / n)
        fdraw = rng.multinomial(int(frequency.sum()), frequency / frequency.sum())
        draws[boot] = draw
        percentiles = reference_percentiles(multiplicity, keys, fdraw)
        for ci, mask in enumerate(masks(percentiles)):
            if ci:
                groups[boot, mask] = ci
            weights = draw * mask
            totals[boot, ci] = weights.sum()
            reps[boot, ci] = np.bincount(
                bins, weights=values * weights[eids], minlength=size)
        if progress and boot % 100 == 0:
            print('BOOTSTRAP', system, estimator_index, boot, flush=True)
    return reps, totals, groups, draws
