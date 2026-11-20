import collections
import math
import unittest
from core import certificates, checked_audits, decode, uniform, wrap, sector, accept, percentile, cent_accept


def fixture(origin=1, pair=1):
    cert = 'FD_SOURCE event=1 pair=%d origin=%d side=1 a=0 b=0 parent=0 first=4 second=-4' % (pair, origin)
    if origin == 4:
        cert = 'FD_SOURCE event=1 pair=1 origin=4 side=1 a=4 b=-4 parent=0 first=1 second=2'
    rows = []
    for st in (21, 8, 0):
        for leg in (1, -1):
            rows.append(dict(id=4*leg if st==21 else -140*leg, ist=st, ity=30 if st==21 else 60,
                             px=3*leg, py=0., pz=0., e=0. if st==21 else 1.86483,
                             fdPair=pair, fdTrack=2*pair+(leg<0), fdLeg=leg, fdOrigin=origin, fdReason=0))
    return {k:[r[k] for r in rows] for k in rows[0]}, certificates(cert)


class Tests(unittest.TestCase):
    def test_certificates(self):
        v, c = fixture()
        for text in ['FD_SOURCE event=1 pair=1', 'FD_SOURCE event=0 pair=1 origin=1 side=0 a=0 b=0 parent=0 first=4 second=-4']:
            self.assertRaises(ValueError, certificates, text)
    def test_mandatory_audits(self):
        line='prefix FD_AUDIT event=2 sl_mismatch=0 shower_shape_errors=0 sea_mismatch=0 carrier_errors=0 truncated_known=0'
        self.assertEqual(set(checked_audits(line,1)),{2})
        self.assertEqual(checked_audits(line.replace('truncated_known=0','truncated_known=114'),1)[2]['truncated_known'],114)
        self.assertRaises(ValueError,checked_audits,line.replace('carrier_errors=0','carrier_errors=1'),1)
        self.assertRaises(ValueError,checked_audits,line+'\n'+line,2)
        self.assertRaises(ValueError,checked_audits,line,2)
    def test_join_and_order(self):
        v,c=fixture();a=collections.Counter();p,_=decode(v,1,c,a)
        self.assertEqual(len(p),1);self.assertIsNotNone(p[0]['pre']);self.assertIsNotNone(p[0]['final'])
        w={k:list(reversed(x)) for k,x in v.items()};q,_=decode(w,1,c,collections.Counter())
        self.assertEqual(p[0]['initial'][0]['id'],q[0]['initial'][0]['id'])
    def test_missing_pre_not_drop_primary(self):
        v,c=fixture();v={k:x[:2]+x[4:] for k,x in v.items()};p,_=decode(v,1,c,collections.Counter())
        self.assertIsNone(p[0]['pre']);self.assertIsNotNone(p[0]['final'])
    def test_duplicate_unknown_contradiction(self):
        v,c=fixture();v={k:x+[x[0]] for k,x in v.items()};p,_=decode(v,1,c,collections.Counter());self.assertEqual(p,[])
        v,c=fixture();p,_=decode(v,1,{},collections.Counter());self.assertEqual(p,[])
        v,c=fixture();v['fdReason'][0]=3;p,_=decode(v,1,c,collections.Counter());self.assertEqual(p,[])
        v,c=fixture();v['fdTrack'][0]=99;p,_=decode(v,1,c,collections.Counter());self.assertEqual(p,[])
    def test_origin4_distinct(self):
        v,c=fixture(4);p,_=decode(v,1,c,collections.Counter());self.assertEqual(p[0]['origin'],4)
    def test_angles_and_selection(self):
        self.assertAlmostEqual(wrap(2*math.pi+.1),.1)
        a=dict(phi=0.,pt=3.,eta=0.,y=0.);b=dict(a,phi=math.pi)
        self.assertTrue(sector(a,b,0.,'parallel'));self.assertFalse(sector(a,b,0.,'perpendicular'))
        self.assertTrue(accept(a,b,'tight'));self.assertFalse(accept(dict(a,pt=2),b,'tight'))
    def test_independent_keys_and_ties(self):
        self.assertNotEqual(uniform('fileA/event1'),uniform('fileB/event1'))
        ref={0:10,1:10};self.assertLess(percentile(1,'x',ref),50);self.assertGreaterEqual(percentile(0,'x',ref),50)
        self.assertRaises(ValueError,percentile,1,'x',{})
        self.assertTrue(cent_accept(100,'cent_60_100'))
        self.assertFalse(cent_accept(10,'cent_0_10'))
    def test_os_ss_unique_pairs_and_zero_event(self):
        ids=[-140,-140,140];os=sum(a==-b for i,a in enumerate(ids) for b in ids[i+1:])
        ss=sum(a==b for i,a in enumerate(ids) for b in ids[i+1:])
        self.assertEqual((os,ss),(2,1));self.assertEqual(((os-ss)+0)/2,.5)
    def test_signed_change_not_folded_first(self):
        initial=-3.;final=3.;self.assertAlmostEqual(math.cos(wrap(final-initial)),math.cos(6.))


if __name__=='__main__':unittest.main()
