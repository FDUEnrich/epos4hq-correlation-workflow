"""Traditional TH1D/TH2D with event/MB bootstrap covariance."""
import json
import math
import numpy as np


def th1(values,variances,low=0.,high=math.pi,title=''):
    from uproot.writing.identify import to_TAxis,to_TH1x
    values=np.asarray(values,dtype=np.float64);var=np.asarray(variances,dtype=np.float64)
    centers=np.linspace(low,high,len(values)+1);centers=(centers[1:]+centers[:-1])/2
    return to_TH1x(fName=None,fTitle=title,data=np.r_[0.,values,0.],fEntries=float(np.abs(values).sum()),
                   fTsumw=float(values.sum()),fTsumw2=float(np.nansum(var)),
                   fTsumwx=float(np.dot(values,centers)),fTsumwx2=float(np.dot(values,centers**2)),
                   fSumw2=np.r_[0.,var,0.],fXaxis=to_TAxis(fName='xaxis',fTitle='',fNbins=len(values),fXmin=low,fXmax=high))


def histogram_output(f,path,raw,rep,nevents=None,lo=0.,hi=math.pi):
    raw=np.asarray(raw);width=(hi-lo)/len(raw)
    rawcov=np.atleast_2d(np.cov(rep,rowvar=False,ddof=1))
    f[path+'/sum']=th1(raw,np.diag(rawcov),lo,hi,'raw pair counts; bootstrap includes events and MB')
    f[path+'/sum_cov']=(rawcov,np.linspace(lo,hi,len(raw)+1),np.linspace(lo,hi,len(raw)+1))
    total=float(raw.sum());areas=rep.sum(axis=1);area_error=float(np.std(areas,ddof=1))
    snr=total/area_error if area_error>0 else None
    warning=total<=0 or not np.all(areas>0) or (snr is not None and snr<5)
    valid=total>0 and not warning
    f[path+'/normalization_status']=json.dumps(dict(area=total,point_valid=total>0,errors_valid=bool(valid),
                                                  bootstrap_valid=int(np.sum(areas>0)),bootstrap_total=len(rep),
                                                  area_error=area_error,signal_to_noise=snr,normalization_warning=bool(warning)))
    if total>0:
        density=raw/total/width
        normrep=rep[areas>0]/areas[areas>0,None]/width
        cov=np.cov(normrep,rowvar=False,ddof=1) if len(normrep)>1 else np.full((len(raw),len(raw)),np.nan)
        var=np.diag(cov) if valid else np.full(len(raw),np.nan)
        f[path+'/unit_area']=th1(density,var,lo,hi,'unit-area shape; inspect normalization_status')
        if valid:f[path+'/unit_area_cov']=(cov,np.linspace(lo,hi,len(raw)+1),np.linspace(lo,hi,len(raw)+1))
        display=raw.reshape(10,-1).sum(axis=1);dr=rep.reshape(len(rep),10,-1).sum(axis=2)
        da=dr.sum(axis=1);ok=da>0
        dc=np.cov(dr[ok]/da[ok,None]/((hi-lo)/10),rowvar=False,ddof=1) if ok.sum()>1 else np.full((10,10),np.nan)
        f[path+'/display10']=th1(display/total/((hi-lo)/10),np.diag(dc) if valid else np.full(10,np.nan),lo,hi)
    if nevents is not None:
        n,nrep=nevents
        if n>0:
            means=np.divide(rep,nrep[:,None]*width,out=np.full(rep.shape,np.nan),where=nrep[:,None]>0)
            good=np.all(np.isfinite(means),axis=1)
            cv=np.cov(means[good],rowvar=False,ddof=1) if good.sum()>1 else np.full((len(raw),len(raw)),np.nan)
            f[path+'/event_mean']=th1(raw/n/width,np.diag(cv),lo,hi)
    return rawcov

