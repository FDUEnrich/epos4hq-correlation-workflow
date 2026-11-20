#include "PilotTrees.h"
#include <TH1D.h>
#include <TH2D.h>
#include <TNamed.h>
#include <TParameter.h>
#include <TCanvas.h>
#include <TGraph.h>
#include <TLegend.h>
#include <TLatex.h>
#include <TLine.h>
#include <TStyle.h>
#include <TColor.h>
#include <TSystem.h>
#include <TROOT.h>
#include <array>
#include <map>
#include <vector>
#include <set>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <numeric>
#include <stdexcept>

namespace origincompare {
constexpr int nb=30, ns=11, no=7;
const double pi=std::acos(-1.), width=pi/nb;
const char* selections[ns]={"angle30","angle45","angle60","pt_both_0_1","pt_both_1_2p5","pt_both_2p5_5","pt_one_gt5_other_gt2p5","eta_lt1","eta_lt2","eta_lt3","eta_lt4"};
const char* cohorts[2]={"finalD0","legacyPromptD0"};
const char* directions[2]={"parallel","perpendicular"};
const char* observables[no]={"OS","SSpp","SSmm","OS_minus_SS","same_vertex","same_companion","same_resolved_relation"};
using Bins=std::array<double,nb>;
using Counts=std::array<std::array<std::array<std::array<Bins,no>,2>,ns>,2>;
struct Particle {int row,id,pair,track,leg,origin;double phi,pt,eta;bool legacy;};
void check(bool t,const std::string&s){if(!t)throw std::runtime_error(s);}
double folded(double a,double b){return std::acos(std::max(-1.,std::min(1.,std::cos(a-b))));}
bool sector(double phi,double axis,double angle){double d=folded(phi,axis);return std::min(d,pi-d)<=angle*pi/180.;}
bool select(const Particle&a,const Particle&b,int s,int d,double ep){
  double angle=s<3?30.+15.*s:45., eta=s>=7?s-6.:4.;
  if(!(std::abs(a.eta)<eta&&std::abs(b.eta)<eta))return false;
  if(!sector(a.phi,ep+d*pi/2,angle)||!sector(b.phi,ep+d*pi/2,angle))return false;
  if(s==3)return a.pt>=0&&a.pt<1&&b.pt>=0&&b.pt<1;
  if(s==4)return a.pt>=1&&a.pt<2.5&&b.pt>=1&&b.pt<2.5;
  if(s==5)return a.pt>=2.5&&a.pt<5&&b.pt>=2.5&&b.pt<5;
  if(s==6)return std::max(a.pt,b.pt)>5&&std::min(a.pt,b.pt)>2.5;
  return true;
}
bool same(const Particle&a,const Particle&b){return a.pair>0&&a.pair==b.pair&&a.id==-b.id&&a.track!=b.track&&a.leg==-b.leg&&a.origin==b.origin;}
double total(const Bins&a){return std::accumulate(a.begin(),a.end(),0.);}
bool normalize(const Bins&a,Bins&out){double t=total(a);out={};if(!(t>0))return false;for(int b=0;b<nb;++b)out[b]=a[b]/(t*width);return true;}
void fill(Counts&out,const std::vector<Particle>&p,double ep){
  for(size_t i=0;i<p.size();++i)for(size_t j=i+1;j<p.size();++j){
    const auto&a=p[i];const auto&b=p[j];int bin=std::min(nb-1,int(folded(a.phi,b.phi)/width));
    int sign=a.id==-b.id?0:(a.id<0?1:2);
    for(int c=0;c<2;++c){if(c&&(!a.legacy||!b.legacy))continue;
      for(int s=0;s<ns;++s)for(int d=0;d<2;++d)if(select(a,b,s,d,ep)){
        ++out[c][s][d][sign][bin];
        out[c][s][d][3][bin]+=sign==0?1.:-1.;
        if(same(a,b)){++out[c][s][d][a.origin==4?5:4][bin];++out[c][s][d][6][bin];}
      }
    }
  }
}
void unitTest(){
  check(sector(0,0,45)&&sector(pi,0,45)&&!sector(pi/2,0,45),"opposed axes");
  Particle a{0,-140,1,2,1,1,0,5.1,0,true},b{1,140,1,3,-1,1,pi,2.6,0,true};
  check(select(a,b,6,0,0)&&select(b,a,6,0,0),"symmetric asymmetric-pT cut");
  a.pt=5.;check(!select(a,b,6,0,0),"strict pT threshold");a.pt=5.1;
  check(same(a,b),"known pair");a.pair=b.pair=0;check(!same(a,b),"never match unknown IDs");
  a.pair=b.pair=1;
  Particle c=a;c.row=2;c.pair=2;c.track=4;c.phi=.01;
  Counts toy{};fill(toy,{a,b,c},0);
  check(total(toy[0][1][0][0])==2&&total(toy[0][1][0][1])==1&&total(toy[0][1][0][2])==0,"unordered OS/SS counting");
  check(total(toy[0][1][0][3])==1&&total(toy[0][1][0][4])==1,"subtract counts and strict pair");
  Bins norm;check(normalize(toy[0][1][0][3],norm),"positive difference integral");
  check(norm[0]<0&&std::abs(total(norm)*width-1)<1e-12,"preserve negative bins, normalize afterwards");
  Bins zero{};check(!normalize(zero,norm),"zero area invalid");zero[0]=-1;check(!normalize(zero,norm),"negative area invalid");
  check(std::abs(folded(.2,2*pi-.2)-.4)<1e-12,"phi wrapping");
  a.origin=b.origin=4;Counts sea{};fill(sea,{a,b},0);
  check(total(sea[0][1][0][4])==0&&total(sea[0][1][0][5])==1&&total(sea[0][1][0][6])==1,"separate EOL and explicit vertex");
}
struct Certificate {int origin,side,a,b,parent,first,second;};
std::map<std::pair<int,int>,Certificate> readCertificates(const std::string&path){
  std::ifstream f(path);check(bool(f),"missing immutable source log");
  std::map<std::pair<int,int>,Certificate> all;std::string line;
  while(std::getline(f,line)){
    auto start=line.find("FD_SOURCE ");if(start==std::string::npos)continue;
    check(line.find("FD_SOURCE ",start+10)==std::string::npos,"multiple source records on one line");
    std::istringstream in(line.substr(start+10));std::map<std::string,int> v;
    for(auto k:{"event","pair","origin","side","a","b","parent","first","second"}){
      std::string word,prefix=std::string(k)+"=";
      check(bool(in>>word)&&word.find(prefix)==0,"malformed/truncated source certificate");
      std::string number=word.substr(prefix.size());size_t used=0;
      int value=std::stoi(number,&used);
      check(used==number.size(),"noninteger source value");v[k]=value;
    }
    std::string trailing;check(!(in>>trailing),"extra source fields");
    for(auto k:{"event","pair","origin","side","a","b","parent","first","second"})check(v.count(k),"incomplete source certificate");
    int o=v["origin"];bool valid=false;
    if(o==1)valid=std::abs(v["a"])!=4&&std::abs(v["b"])!=4&&std::abs(v["first"])==4&&v["first"]==-v["second"];
    if(o==2)valid=std::abs(v["a"])==4&&v["a"]==-v["b"]&&v["parent"]>0&&v["first"]>0&&v["second"]>0&&v["first"]!=v["second"];
    if(o==3)valid=v["a"]==0&&std::abs(v["b"])==4&&(v["side"]==1||v["side"]==2);
    if(o==4)valid=std::abs(v["a"])==4&&v["a"]==-v["b"]&&(v["side"]==1||v["side"]==2)&&v["first"]>0;
    check(valid&&v["pair"]>0&&v["event"]>0,"invalid generator source evidence");
    check(all.emplace(std::make_pair(v["event"],v["pair"]),Certificate{o,v["side"],v["a"],v["b"],v["parent"],v["first"],v["second"]}).second,"reused event-local source identity");
  }
  check(!all.empty(),"no source certificates");return all;
}
}

// Bounded validation sample only. No centrality percentiles are inferred here.
void CompareOriginSubtraction(const char* path="--self-test",const char* system="",const char* output="",const char* sourceLog="",int requested=0){
  using namespace origincompare;
  try{
    unitTest();if(std::string(path)=="--self-test"){std::cout<<"ORIGIN_SUBTRACTION_TEST_PASS\n";return;}
    check(std::string(system)=="PbPb"||std::string(system)=="OO","invalid system");
    auto certificates=readCertificates(sourceLog);TFile input(path,"READ");auto tree=checkedTree(input,"teposevent");check(tree,"invalid tree or aliases");
    check(requested>=tree->GetEntries()&&requested>=2&&requested<=1000,"invalid bounded pilot event budget");
    const char* required[]={"np","id","ist","ity","zus","px","py","pz","phi","phir","fdPair","fdTrack","fdLeg","fdOrigin","fdReason","fdEvent","fdLineageVersion"};
    for(auto name:required)check(tree->GetLeaf(name),std::string("missing ")+name);
    auto v=[&](const char*n,int i=0){return tree->GetLeaf(n)->GetValue(i);};
    std::string out(output);check(!out.empty()&&gSystem->AccessPathName(out.c_str()),"refuse existing output");check(gSystem->mkdir(out.c_str(),true)==0,"mkdir failed");
    std::vector<Counts> events(requested);Counts sum{};std::set<int> eventIds;
    long initial=0,knownInitial=0,finalD=0,knownD=0,strictPairs=0,companionPairs=0;
    std::map<int,long> initialOrigins,finalOrigins,unknownReasons;
    std::ofstream pairs(out+"/same_origin_pairs.csv");pairs<<std::setprecision(17)<<"entry,fdEvent,pair,origin,row_c,row_cbar,track_c,track_cbar,delta_phi,legacy_both\n";
    for(Long64_t e=0;e<tree->GetEntries();++e){
      check(tree->GetEntry(e)>0,"unreadable event");int ev=v("fdEvent");check(v("fdLineageVersion")==4,"wrong lineage version");check(eventIds.insert(ev).second,"duplicate event");
      check(ev>0&&ev<=requested,"event ID out of budget");int n=v("np");check(n>0&&n<=350000,"bad particle count");
      double ep=v("phi")+v("phir");check(std::isfinite(ep),"invalid event plane");
      std::map<int,int> initials,finalTracks;std::vector<Particle> selected;
      for(int i=0;i<n;++i){
        int id=v("id",i),st=v("ist",i),p=v("fdPair",i),tr=v("fdTrack",i),leg=v("fdLeg",i),o=v("fdOrigin",i),why=v("fdReason",i);
        if(p){
          check(p>0&&(leg==1||leg==-1)&&tr==2*p+(leg<0)&&why==0&&o>=1&&o<=4,"malformed tag");
          auto cert=certificates.find({ev,p});check(cert!=certificates.end()&&cert->second.origin==o,"tag lacks source certificate");
          check(std::abs(id)==4||std::abs(id)>=100,"known tag on non-charm elementary record");
        }
        if(std::abs(id)==4&&st==21){++initial;if(p){++knownInitial;++initialOrigins[o];check(id*leg>0,"initial charm sign");check(++initials[tr]==1,"duplicate initial carrier");}}
        if(std::abs(id)!=140||(st!=0&&st!=1))continue;
        ++finalD;if(p){++knownD;++finalOrigins[o];check(id*leg<0,"D0 charm sign");check(++finalTracks[tr]==1,"duplicate final D0 carrier");}else ++unknownReasons[why];
        double px=v("px",i),py=v("py",i),pz=v("pz",i),pt=std::hypot(px,py);check(std::isfinite(pt)&&std::isfinite(pz),"invalid momentum");if(pt<=1e-6)continue;
        bool legacy=v("ity",i)==60&&(std::abs(v("zus",i)+2)<.25||std::abs(v("zus",i)+1)<.25);
        selected.push_back({i,id,p,tr,leg,o,std::atan2(py,px),pt,std::asinh(pz/pt),legacy});
      }
      for(auto x:finalTracks)check(initials[x.first]==1,"final D0 lacks unique initial charm carrier");
      for(size_t i=0;i<selected.size();++i)for(size_t j=i+1;j<selected.size();++j)if(same(selected[i],selected[j])){
        auto a=selected[i],b=selected[j];if(a.leg<0)std::swap(a,b);
        (a.origin==4?companionPairs:strictPairs)++;
        pairs<<e<<','<<ev<<','<<a.pair<<','<<a.origin<<','<<a.row<<','<<b.row<<','<<a.track<<','<<b.track<<','<<folded(a.phi,b.phi)<<','<<(a.legacy&&b.legacy)<<'\n';
      }
      fill(events[e],selected,ep);
    }
    pairs.close();
    for(auto&ec:events)for(int c=0;c<2;++c)for(int s=0;s<ns;++s)for(int d=0;d<2;++d)for(int o=0;o<no;++o)for(int b=0;b<nb;++b)sum[c][s][d][o][b]+=ec[c][s][d][o][b];
    TH1::AddDirectory(false);gROOT->SetBatch(true);gStyle->SetOptStat(0);
    TFile dest((out+"/origin_vs_count_subtraction.root").c_str(),"CREATE");check(!dest.IsZombie(),"ROOT output failed");
    TNamed("definition","OS=N(D0 antiD0); SS=N(D0 D0)+N(antiD0 antiD0); unordered pairs; subtract raw counts THEN normalize; signed bins retained").Write();
    TNamed("lineage_definition","origins 1/2/3=explicit Born/SL/TL pair vertices; origin4=explicit heavy-sea endpoint-companion relation, not a resolved hard vertex; unknown=excluded from truth only").Write();
    TNamed("cohort_definition","finalD0: all ist=0/1 D0/antiD0 including cascade descendants, not an experimental prompt claim; legacyPromptD0: ity60 zus-2/-1; same event/cut pool for truth and OS-SS within each cohort").Write();
    TNamed("plane_selection","transverse_momentum_phi; thetaEP=phi+phir; both particles within same bidirectional axis +/- half-angle").Write();
    TNamed("sample_status","VALIDATION_PILOT_ONLY; no centrality catalog; statistical covariance is event-delete-one jackknife, invalid if any replicate normalization is nonpositive").Write();
    std::ofstream csv(out+"/distributions.csv"),cov(out+"/covariances.csv"),rat(out+"/comparison_ratios.csv");
    csv<<std::setprecision(17)<<"cohort,selection,direction,observable,bin_low,bin_high,raw_count,density,normalization_valid,jackknife_valid\n";
    cov<<std::setprecision(17)<<"cohort,selection,direction,observable,mode,bin_i,bin_j,covariance,valid\n";
    rat<<std::setprecision(17)<<"cohort,selection,direction,bin_low,bin_high,same_relation_density_over_subtracted_density,valid\n";
    const int display[3]={4,6,3};const int colors[3]={TColor::GetColor("#009E73"),TColor::GetColor("#0072B2"),TColor::GetColor("#D55E00")};
    const char* labels[3]={"Explicit pair vertex","Vertex + EOL companion","OS - (SS++ + SS--)"};
    for(int c=0;c<2;++c)for(int s=0;s<ns;++s){
      std::array<std::array<Bins,no>,2> density{};bool valid[2][no]{};bool jk[2][no]{};
      for(int d=0;d<2;++d)for(int o=0;o<no;++o){
        auto raw=sum[c][s][d][o];valid[d][o]=normalize(raw,density[d][o]);
        std::vector<Bins> reps(requested);jk[d][o]=valid[d][o];
        for(int e=0;e<requested;++e){Bins leave=raw;for(int b=0;b<nb;++b)leave[b]-=events[e][c][s][d][o][b];if(!normalize(leave,reps[e]))jk[d][o]=false;}
        std::string key=std::string(cohorts[c])+"__"+selections[s]+"__"+directions[d]+"__"+observables[o];
        TH1D h((key+"__count").c_str(),"raw counts",nb,0,pi),norm((key+"__density").c_str(),"signed unit-area density",nb,0,pi);
        for(int b=0;b<nb;++b){h.SetBinContent(b+1,raw[b]);if(valid[d][o])norm.SetBinContent(b+1,density[d][o][b]);
          csv<<cohorts[c]<<','<<selections[s]<<','<<directions[d]<<','<<observables[o]<<','<<b*width<<','<<(b+1)*width<<','<<raw[b]<<',';if(valid[d][o])csv<<density[d][o][b];csv<<','<<valid[d][o]<<','<<jk[d][o]<<'\n';}
        h.Write();if(valid[d][o])norm.Write();TParameter<int>((key+"__normalization_valid").c_str(),valid[d][o]).Write();TParameter<int>((key+"__jackknife_valid").c_str(),jk[d][o]).Write();
        for(int mode=0;mode<2;++mode){bool ok=!mode||jk[d][o];TH2D matrix((key+(mode?"__density_cov":"__count_cov")).c_str(),"event statistical covariance",nb,0,pi,nb,0,pi);
          Bins mean{};if(mode&&ok)for(auto&r:reps)for(int b=0;b<nb;++b)mean[b]+=r[b]/requested;
          for(int i=0;i<nb;++i)for(int j=0;j<nb;++j){double value=0;
            if(ok)for(int e=0;e<requested;++e){if(mode)value+=(reps[e][i]-mean[i])*(reps[e][j]-mean[j])*(requested-1.)/requested;
              else value+=(events[e][c][s][d][o][i]-raw[i]/requested)*(events[e][c][s][d][o][j]-raw[j]/requested)*requested/(requested-1.);}
            if(ok)matrix.SetBinContent(i+1,j+1,value);
            cov<<cohorts[c]<<','<<selections[s]<<','<<directions[d]<<','<<observables[o]<<','<<(mode?"density":"count")<<','<<i<<','<<j<<',';if(ok)cov<<value;cov<<','<<ok<<'\n';
          }if(ok)matrix.Write();
        }
      }
      TCanvas canvas("comparison","Origin versus OS-SS",1500,1250);canvas.Divide(2,3);
      std::array<std::array<std::array<TGraph,3>,2>,2> graphs;
      std::array<std::array<TH1D,2>,3> frames;
      std::array<std::array<TLegend,2>,2> legends;
      std::array<TGraph,2> ratios;std::array<TLine,2> lines;
      for(int mode=0;mode<2;++mode){double low=0,high=1;
        for(int d=0;d<2;++d)for(int k=0;k<3;++k){int o=display[k];if(mode&&!valid[d][o])continue;for(double y:(mode?density[d][o]:sum[c][s][d][o])){low=std::min(low,y);high=std::max(high,y);}}
        for(int d=0;d<2;++d){canvas.cd(1+d+2*mode);gPad->SetLeftMargin(.14);gPad->SetBottomMargin(.13);gPad->SetTopMargin(.23);
          auto&frame=frames[mode][d];frame.SetBins(nb,0,pi);frame.SetMinimum(low<0?low*1.25:0);frame.SetMaximum(high*1.2);frame.GetXaxis()->SetTitle("|#Delta#phi| (rad)");frame.GetYaxis()->SetTitle(mode?"Signed unit-area density (rad^{-1})":"Pair counts / bin");frame.Draw("AXIS");
          auto&legend=legends[mode][d];legend.SetX1NDC(.16);legend.SetY1NDC(.79);legend.SetX2NDC(.92);legend.SetY2NDC(.9);legend.SetNColumns(1);legend.SetTextSize(.03);legend.SetBorderSize(0);legend.SetFillStyle(0);
          for(int k=0;k<3;++k){int o=display[k];auto&g=graphs[mode][d][k];g.SetLineColor(colors[k]);g.SetLineStyle(k+1);g.SetLineWidth(2);g.SetMarkerColor(colors[k]);g.SetMarkerStyle(20+k);
            if(!mode||valid[d][o])for(int b=0;b<nb;++b)g.SetPoint(b,(b+.5)*width,mode?density[d][o][b]:sum[c][s][d][o][b]);
            if(g.GetN()){g.Draw("LP SAME");legend.AddEntry(&g,labels[k],"lp");}}
          legend.Draw();TLatex text;text.SetNDC();text.SetTextSize(.032);text.DrawLatex(.14,.945,(std::string(system)+" / "+cohorts[c]+" / "+selections[s]+" / "+directions[d]).c_str());
          text.SetTextSize(.028);if(mode&&(!valid[d][3]||!valid[d][6]))text.DrawLatex(.2,.6,"Missing curve: nonpositive total, normalization undefined");
        }
      }
      double rlow=0,rhigh=2;
      for(int d=0;d<2;++d)for(int b=0;b<nb;++b){bool ok=valid[d][6]&&valid[d][3]&&density[d][3][b]!=0;double r=ok?density[d][6][b]/density[d][3][b]:0;
        rat<<cohorts[c]<<','<<selections[s]<<','<<directions[d]<<','<<b*width<<','<<(b+1)*width<<',';if(ok){rat<<r;ratios[d].SetPoint(ratios[d].GetN(),(b+.5)*width,r);rlow=std::min(rlow,r);rhigh=std::max(rhigh,r);}rat<<','<<ok<<'\n';}
      for(int d=0;d<2;++d){canvas.cd(5+d);gPad->SetLeftMargin(.14);gPad->SetBottomMargin(.14);auto&f=frames[2][d];f.SetBins(nb,0,pi);f.SetMinimum(rlow<0?rlow*1.1:0);f.SetMaximum(rhigh*1.1);f.GetXaxis()->SetTitle("|#Delta#phi| (rad)");f.GetYaxis()->SetTitle("P_{relation} / P_{OS-SS}");f.Draw("AXIS");
        ratios[d].SetMarkerStyle(20);ratios[d].SetMarkerSize(.7);if(ratios[d].GetN())ratios[d].Draw("P SAME");lines[d]=TLine(0,1,pi,1);lines[d].SetLineStyle(2);lines[d].Draw();
        TLatex text;text.SetNDC();text.SetTextSize(.029);text.DrawLatex(.15,.93,"PILOT ONLY; zero denominators masked; no significance claim");}
      std::string stem=out+"/"+cohorts[c]+"__"+selections[s];canvas.Print((stem+".pdf").c_str());canvas.Print((stem+".png").c_str());canvas.Clear();
    }
    dest.Close();csv.close();cov.close();rat.close();
    std::ofstream audit(out+"/COMPARISON_AUDIT.json");audit<<"{\"status\":\"VALIDATION_PILOT_ONLY\",\"system\":\""<<system<<"\",\"requested_events\":"<<requested<<",\"stored_events\":"<<tree->GetEntries()<<",\"initial_charm\":"<<initial<<",\"tagged_initial_charm\":"<<knownInitial<<",\"final_D0\":"<<finalD<<",\"tagged_final_D0\":"<<knownD<<",\"explicit_vertex_D0_pairs\":"<<strictPairs<<",\"companion_D0_pairs\":"<<companionPairs<<",\"valid_for_production\":false,\"ss_convention\":\"SSpp+SSmm\",\"normalization\":\"subtract counts before unit-area; nonpositive total undefined\",\"source_counts_include_rejected_attempts\":true,\"centrality_catalog\":null}\n";
    std::ofstream coverage(out+"/coverage.csv");coverage<<"stage,origin_or_unknown_reason,count\n";for(auto x:initialOrigins)coverage<<"initial_known,"<<x.first<<','<<x.second<<'\n';for(auto x:finalOrigins)coverage<<"final_D0_known,"<<x.first<<','<<x.second<<'\n';for(auto x:unknownReasons)coverage<<"final_D0_unknown,"<<x.first<<','<<x.second<<'\n';
    std::cout<<"ORIGIN_COMPARISON_PASS strict_pairs="<<strictPairs<<" companion_pairs="<<companionPairs<<" tagged_initial="<<knownInitial<<'/'<<initial<<" PILOT_ONLY\n";
  }catch(const std::exception&e){std::cerr<<"ORIGIN_COMPARISON_FAIL "<<e.what()<<std::endl;gSystem->Exit(85);}
}
