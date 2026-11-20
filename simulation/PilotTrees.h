#ifndef FD_PILOT_TREES_H
#define FD_PILOT_TREES_H
#include <TFile.h>
#include <TTree.h>
#include <TLeaf.h>
#include <cmath>
#include <iostream>
#include <cstring>
#include <string>
inline bool compareTrees(TTree* a,TTree* b,long long& values,long long& bad) {
  if(!a || !b || a->GetEntries()!=b->GetEntries()) {++bad;return false;}
  for(Long64_t e=0;e<a->GetEntries();++e) {
    if(a->GetEntry(e)<=0 || b->GetEntry(e)<=0) {++bad;continue;}
    auto leaves=a->GetListOfLeaves();
    for(int l=0;l<leaves->GetEntries();++l) {
      auto p=dynamic_cast<TLeaf*>(leaves->At(l)); auto q=b->GetLeaf(p->GetName());
      if(!q || std::strcmp(p->GetTypeName(),q->GetTypeName()) || p->GetNdata()!=q->GetNdata()) {++bad;continue;}
      for(int k=0;k<p->GetNdata();++k) {
        ++values; double u=p->GetValue(k),v=q->GetValue(k);
        if(!std::isfinite(u)||!std::isfinite(v)||u!=v) {
          if(bad<10)std::cerr<<"DIFF "<<a->GetName()<<" event="<<e<<" leaf="<<p->GetName()<<" row="<<k<<" "<<u<<" "<<v<<std::endl;
          ++bad;
        }
      }
    }
  }
  return bad==0;
}
inline TTree* checkedTree(TFile& f,const char* name) {
  if(f.IsZombie()||f.TestBit(TFile::kRecovered)) return nullptr;
  auto t=dynamic_cast<TTree*>(f.Get(name));
  // These are two writer aliases of one stream, never two independent samples.
  auto alias=dynamic_cast<TTree*>(f.Get((std::string(name)+"0").c_str()));
  if(!t||!alias) return nullptr;
  long long values=0,bad=0;
  if(!compareTrees(t,alias,values,bad)) return nullptr;
  return t;
}
#endif
