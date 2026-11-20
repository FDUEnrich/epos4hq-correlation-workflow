#include "CompareOriginSubtraction.C"
#include <memory>

void ValidateProduction(const char* path,const char* sourceLog,const char* output,
                const char* system,int requested,int skipped,int expectedVersion=5) {
  using namespace origincompare;
  try {
    unitTest();
    check(requested>0 && skipped>=0 && skipped<=requested,"invalid accounting");
    int retained=requested-skipped;
    std::unique_ptr<TFile> file;
    TTree* tree=nullptr;
    if(!gSystem->AccessPathName(path)) {
      file.reset(TFile::Open(path,"READ"));
      check(file&&!file->IsZombie()&&!file->TestBit(TFile::kRecovered),"invalid ROOT");
      tree=checkedTree(*file,"teposevent");
      check(tree||(!retained&&!file->Get("teposevent")&&!file->Get("teposevent0")),"invalid event aliases");
      auto head=checkedTree(*file,"teposhead");
      check(head||!retained,"missing header");
      if(head)check(head->GetEntries()==1&&head->GetEntry(0)>0&&head->GetLeaf("nfull")&&head->GetLeaf("nfull")->GetValue()==requested,"header budget");
    } else check(!retained,"missing nonempty ROOT");
    check(!retained||(tree&&tree->GetEntries()==retained),"event count");
    std::map<std::pair<int,int>,Certificate> certificates;
    if(retained)certificates=readCertificates(sourceLog);
    const char* arrays[]={"id","ist","ity","zus","px","py","pz","fdPair","fdTrack","fdLeg","fdOrigin","fdReason"};
    if(retained){for(auto a:arrays)check(tree->GetLeaf(a),std::string("missing ")+a);for(auto a:{"np","fdEvent","fdLineageVersion","phi","phir"})check(tree->GetLeaf(a),std::string("missing ")+a);}
    std::set<int> events;
    long long initial=0,knownInitial=0,finalD=0,knownD=0,strictD=0,companionD=0;
    for(int entry=0;entry<retained;++entry){
      check(tree->GetEntry(entry)>0,"event read");
      auto v=[&](const char* n,int i=0){return tree->GetLeaf(n)->GetValue(i);};
      int ev=v("fdEvent"),np=v("np");
      check(ev>0&&events.insert(ev).second,"duplicate event identity");
      check(v("fdLineageVersion")==expectedVersion,"wrong lineage version");
      check(np>0&&np<=350000,"invalid np");
      check(std::isfinite(v("phi"))&&std::isfinite(v("phir")),"invalid EP");
      for(auto a:arrays)check(tree->GetLeaf(a)->GetNdata()==np,std::string("array length ")+a);
      std::map<int,int> initials,finals;
      for(int i=0;i<np;++i){
        int id=v("id",i),st=v("ist",i),p=v("fdPair",i),track=v("fdTrack",i),leg=v("fdLeg",i),o=v("fdOrigin",i),reason=v("fdReason",i);
        for(auto a:{"px","py","pz"})check(std::isfinite(v(a,i)),"nonfinite momentum");
        if(p){
          check(p>0&&(leg==1||leg==-1)&&track==2*p+(leg<0)&&reason==0&&o>=1&&o<=4,"malformed tag");
          auto c=certificates.find({ev,p});check(c!=certificates.end()&&c->second.origin==o,"missing source certificate");
          check(std::abs(id)==4||std::abs(id)>=100,"tag on noncharm elementary record");
        }else check(!track&&!leg&&!o&&reason>0,"malformed unknown");
        if(std::abs(id)==4&&st==21){++initial;if(p){++knownInitial;check(id*leg>0&&++initials[track]==1,"initial carrier");}}
        if(std::abs(id)==140&&(st==0||st==1)){++finalD;if(p){++knownD;check(id*leg<0&&++finals[track]==1,"final carrier");if(o==4)++companionD;else ++strictD;}}
      }
      for(auto x:finals)check(initials[x.first]==1,"final D0 lacks unique initial carrier");
    }
    std::ofstream out(output);
    check(bool(out),"audit output");
    out<<"{\"status\":\"PASS\",\"system\":\""<<system<<"\",\"requested\":"<<requested<<",\"skipped_no_charm\":"<<skipped<<",\"retained\":"<<retained<<",\"lineage_version\":"<<expectedVersion<<",\"initial_charm\":"<<initial<<",\"tagged_initial_charm\":"<<knownInitial<<",\"D0_status01\":"<<finalD<<",\"tagged_D0_status01\":"<<knownD<<",\"explicit_vertex_D0\":"<<strictD<<",\"companion_D0\":"<<companionD<<",\"event_ids\":[";
    bool first=true;for(int ev:events){if(!first)out<<',';out<<ev;first=false;}out<<"],\"errors\":0}\n";
    out.close();
    std::cout<<"V5_VALIDATION_PASS requested="<<requested<<" retained="<<retained<<" errors=0"<<std::endl;
  }catch(const std::exception& e){std::cerr<<"V5_VALIDATION_FAIL "<<e.what()<<std::endl;gSystem->Exit(85);}
}
