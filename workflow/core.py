"""Certified source identity and generator-level centrality; Python >=3.6.

No row-order, nearest-momentum, or shared-remote-ancestor source inference.
The ROOT `e` branch is mass (EPOS out.f: eam=pptl(5)), not energy.
"""
import collections
import hashlib
import math
import re

PI = math.pi
CENTRALITIES = [('inclusive', 0., 100.), ('cent_0_10', 0., 10.),
                ('cent_20_50', 20., 50.), ('cent_60_100', 60., 100.)]
FIELDS = 'event pair origin side a b parent first second'.split()


def uniform(key):
    return (int(hashlib.sha256(key.encode()).hexdigest()[:13], 16) + .5) / 16.**13


def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))


def delta(a, b):
    return abs(wrap(a['phi'] - b['phi']))


def sector(a, b, ep, direction):
    if direction == 'inclusive':
        return True
    axis = ep + (PI / 2 if direction == 'perpendicular' else 0)
    return all(abs(wrap(2 * (p['phi'] - axis))) <= PI / 2 + 1e-12 for p in (a, b))


def accept(a, b, selection):
    if min(a['pt'], b['pt']) <= 1e-6:
        return False
    if selection == 'wide':
        return max(abs(a['eta']), abs(b['eta'])) < 4
    if selection == 'tight':
        return max(abs(a['y']), abs(b['y'])) < 1 and min(a['pt'], b['pt']) > 2
    raise ValueError('unknown selection')


def certificates(text):
    token = 'FD_SOURCE '
    pat = re.compile(re.escape(token) + ' '.join(k + r'=(-?\d+)' for k in FIELDS) + r'(?=\s|$)')
    found = list(pat.finditer(text))
    if [m.start() for m in found] != [m.start() for m in re.finditer(token, text)]:
        raise ValueError('malformed/truncated source certificate')
    out = {}
    for m in found:
        v = dict(zip(FIELDS, map(int, m.groups())))
        o = v['origin']
        valid = ((o == 1 and abs(v['a']) != 4 and abs(v['b']) != 4 and
                  abs(v['first']) == 4 and v['first'] == -v['second']) or
                 (o == 2 and abs(v['a']) == 4 and v['a'] == -v['b'] and
                  v['parent'] > 0 and v['first'] > 0 and v['second'] > 0 and v['first'] != v['second']) or
                 (o == 3 and v['a'] == 0 and abs(v['b']) == 4 and v['side'] in (1, 2)) or
                 (o == 4 and abs(v['a']) == 4 and v['a'] == -v['b'] and
                  v['side'] in (1, 2) and v['first'] > 0))
        key = (v['event'], v['pair'])
        if not valid or min(key) <= 0 or key in out:
            raise ValueError('invalid or duplicate source evidence')
        out[key] = v
    return out


def checked_audits(text,expected):
    out={}
    for match in re.finditer(r'FD_AUDIT\s+([^\n]*)',text):
        block=match.group(1).split('FD_SOURCE',1)[0]
        pairs=re.findall(r'\b([a-zA-Z_]+)=(-?\d+)',block)
        values={k:int(v) for k,v in pairs}
        mandatory=('event','sl_mismatch','shower_shape_errors','sea_mismatch','carrier_errors')
        if len(values)!=len(pairs) or any(k not in values for k in mandatory):
            raise ValueError('malformed lineage audit')
        # fdtruncate clears tags above a shortened container; this may include
        # historical copies. It is not one of the generator's mandatory error
        # counters and is NOT a count of unique physical carriers lost.
        if any(values[k]!=0 for k in mandatory[1:]):
            raise ValueError('nonzero mandatory lineage error')
        event=values['event']
        if event<=0 or event in out:raise ValueError('duplicate/invalid lineage audit event')
        out[event]=values
    if len(out)!=expected:raise ValueError('lineage audit retained-event count mismatch')
    return out


def charge_table(path):
    """Read the actual EPOS idt.dt column 12, following ids.f idchrg.

    Small codes use the positive-code table and charge conjugation. Rare
    codes >9900 use exact table entries. Unlike idchrg's rare-code default,
    an absent entry is rejected rather than silently assumed neutral.
    """
    rows = {}
    with open(path) as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith('!'):
                continue
            w = line.split()
            if len(w) < 16:
                raise ValueError('malformed generator particle table')
            ident, q = int(w[0]), float(w[11])
            if ident in rows and rows[ident] != q:
                raise ValueError('conflicting generator charge')
            rows[ident] = q
    def charge(ident):
        ident = int(ident)
        if abs(ident) <= 9900:
            if abs(ident) not in rows:
                raise ValueError('charge absent from EPOS table: %d' % ident)
            return rows[abs(ident)] * (-1 if ident < 0 else 1)
        if ident not in rows:
            raise ValueError('rare forward particle absent from charge table: %d' % ident)
        return rows[ident]
    return charge


def kinematics(v, i):
    px, py, pz, mass = [float(v[k][i]) for k in ('px', 'py', 'pz', 'e')]
    if not all(math.isfinite(x) for x in (px, py, pz, mass)) or mass < 0:
        raise ValueError('nonfinite momentum or invalid mass')
    pt = math.hypot(px, py)
    eta = math.asinh(pz / pt) if pt > 0 else math.copysign(float('inf'), pz)
    mt = math.hypot(pt, mass)
    y = math.asinh(pz / mt) if mt > 0 else math.copysign(float('inf'), pz)
    return dict(phi=math.atan2(py, px), pt=pt, eta=eta, y=y, mass=mass,
                id=int(v['id'][i]), row=i)


def multiplicities(v, charge):
    main, far = 0, 0
    for i in range(len(v['id'])):
        if int(v['ist'][i]) != 0:
            continue
        pt = math.hypot(float(v['px'][i]), float(v['py'][i]))
        if not math.isfinite(pt) or not math.isfinite(float(v['pz'][i])):
            raise ValueError('nonfinite final momentum in centrality estimator')
        if pt <= 0:
            continue
        eta = math.asinh(float(v['pz'][i]) / pt)
        forward = 2.8 < eta < 5.1 or -3.7 < eta < -1.7
        alternative = 4 < abs(eta) < 5.5
        if (forward or alternative) and charge(v['id'][i]) != 0:
            main += forward
            far += alternative
    return [main, far]


def decode(v, ev, cert, audit):
    stages = {k: collections.defaultdict(list) for k in ('initial', 'pre', 'final')}
    all_final = []
    for i in range(len(v['id'])):
        ident, st, ity = [int(v[k][i]) for k in ('id', 'ist', 'ity')]
        stage = ('initial' if abs(ident) == 4 and st == 21 else
                 'pre' if abs(ident) == 140 and st in (6, 8) and ity == 60 else
                 'final' if abs(ident) == 140 and st in (0, 1) else None)
        if stage is None:
            continue
        p = kinematics(v, i)
        if abs(ident) == 140 and not 1.6 < p['mass'] < 2.2:
            raise ValueError('D0 mass contract violated; do not treat e as energy')
        if not all(math.isfinite(p[k]) for k in ('phi', 'pt', 'eta', 'y')) or p['pt'] <= 1e-6:
            audit[stage + '_undefined_angle'] += 1
            continue
        if stage == 'final':
            all_final.append(p)
        pair, track, leg, origin, why = [int(v[k][i]) for k in
                                        ('fdPair', 'fdTrack', 'fdLeg', 'fdOrigin', 'fdReason')]
        audit[stage + '_candidates'] += 1
        if pair <= 0 or why != 0:
            audit[stage + '_unknown'] += 1
            continue
        evidence = cert.get((ev, pair))
        if evidence is None:
            audit[stage + '_missing_certificate'] += 1
            continue
        if (leg not in (-1, 1) or track != 2 * pair + (leg < 0) or
                evidence['origin'] != origin or
                (ident * leg <= 0 if stage == 'initial' else ident * leg >= 0)):
            audit[stage + '_contradictory_tag'] += 1
            continue
        p.update(pair=pair, track=track, leg=leg, origin=origin)
        stages[stage][(pair, leg)].append(p)
    for name, mapping in stages.items():
        audit[name + '_duplicate_carrier_keys'] += sum(len(a) != 1 for a in mapping.values())
    pairs = []
    for pair in sorted({k[0] for k in stages['initial']}):
        initial = [stages['initial'].get((pair, leg), []) for leg in (1, -1)]
        if any(len(x) != 1 for x in initial):
            audit['initial_pair_unresolved'] += 1
            continue
        a, b = [x[0] for x in initial]
        if a['origin'] != b['origin'] or a['track'] == b['track']:
            audit['initial_pair_contradictory'] += 1
            continue
        item = dict(pair=pair, origin=a['origin'], initial=[a, b], pre=None, final=None)
        audit['origin_%d_initial_pairs' % a['origin']] += 1
        for name in ('pre', 'final'):
            found = [stages[name].get((pair, leg), []) for leg in (1, -1)]
            if any(len(x) == 0 for x in found):
                audit['origin_%d_%s_missing_D_leg' % (a['origin'], name)] += 1
            if any(len(x) > 1 for x in found):
                audit['origin_%d_%s_ambiguous_D_leg' % (a['origin'], name)] += 1
            if all(len(x) == 1 for x in found):
                h = [x[0] for x in found]
                if (h[0]['origin'] == h[1]['origin'] == a['origin'] and
                        all(h[j]['track'] == initial[j][0]['track'] for j in (0, 1))):
                    item[name] = h
                    audit['origin_%d_%s_pairs' % (a['origin'], name)] += 1
                else:
                    audit[name + '_pair_contradictory'] += 1
        pairs.append(item)
    for name in ('pre', 'final'):
        audit[name + '_no_unique_initial'] += sum(
            len(stages['initial'].get(key, [])) != 1 for key in stages[name])
    return pairs, all_final


def percentile(value, key, reference):
    n = sum(reference.values())
    if n <= 0:
        raise ValueError('empty MB reference')
    above = sum(count for m, count in reference.items() if int(m) > value)
    equal = reference.get(value, reference.get(str(value), 0))
    return min(100., 100 * (above + uniform(key) * equal) / n)


def cent_accept(c, group):
    return group == 'inclusive' or any(name == group and lo <= c and (c < hi or hi == 100 and c == 100)
                                     for name, lo, hi in CENTRALITIES)
