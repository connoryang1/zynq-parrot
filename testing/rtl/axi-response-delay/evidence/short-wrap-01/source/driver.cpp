#include "Vaxi_response_delay_wrapper.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using R = std::array<uint32_t,3>;
static void require(bool value,const std::string& message){if(!value)throw std::runtime_error(message);}
static uint32_t random32(uint32_t& value){value^=value<<13;value^=value>>17;value^=value<<5;return value;}
static R packet(uint64_t nonce,unsigned id,unsigned response,bool last){
    return {{uint32_t(nonce),uint32_t(nonce>>32),uint32_t((id&63)|((response&3)<<6)|(unsigned(last)<<8))}};
}
struct REntry{R data;uint64_t accepted;unsigned delay;uint32_t cycle32;};
struct BEntry{uint8_t data;uint64_t accepted;unsigned delay;uint32_t cycle32;};
struct Delivered{uint64_t accepted,delivered;unsigned delay;uint32_t input32,output32;};
struct Sim{
    std::unique_ptr<VerilatedContext> context{new VerilatedContext};
    std::unique_ptr<Vaxi_response_delay_wrapper> d{new Vaxi_response_delay_wrapper{context.get()}};
    std::unique_ptr<VerilatedFstC> trace{new VerilatedFstC};
    uint64_t clocks=0,time=0,r_in=0,r_out=0,b_in=0,b_out=0,r_reset_drop=0,b_reset_drop=0;
    uint32_t r_stalls=0,b_stalls=0;
    unsigned max_r=0,max_b=0,max_ids=0;
    std::deque<REntry> rq;std::deque<BEntry>bq;std::vector<Delivered>delivered,b_delivered;
    bool held_r=false,held_b=false;R held_r_data{};uint8_t held_b_data=0;
    explicit Sim(){
        context->traceEverOn(true);d->trace(trace.get(),99);trace->open("axi-response-delay.fst");
        d->clk_i=0;d->reset_i=1;d->cfg_v_i=0;d->cfg_safe_i=1;d->cfg_delay_i=0;
        d->r_v_i=d->b_v_i=0;d->r_ready_i=d->b_ready_i=0;d->eval();trace->dump(0);reset();
    }
    ~Sim(){d->final();trace->close();}
    R input()const{return {{d->r_payload_i[0],d->r_payload_i[1],d->r_payload_i[2]}};}
    R output()const{return {{d->r_payload_o[0],d->r_payload_o[1],d->r_payload_o[2]}};}
    void drive(const R& value){for(int i=0;i<3;++i)d->r_payload_i[i]=value[i];}
    void eval(){d->eval();}
    void step(){
        eval();unsigned delay=d->active_delay_o;uint32_t prior_cycle=d->cycle_o;
        bool commit=d->cfg_v_i&&d->cfg_ready_o&&d->cfg_delay_i<=384;
        bool ri=d->r_v_i&&d->r_ready_o,ro=d->r_v_o&&d->r_ready_i;
        bool bi=d->b_v_i&&d->b_ready_o,bo=d->b_v_o&&d->b_ready_i;
        if(!d->reset_i){
            if(held_r)require(d->r_v_o&&output()==held_r_data,"stalled R VALID/payload changed");
            if(held_b)require(d->b_v_o&&d->b_payload_o==held_b_data,"stalled B VALID/payload changed");
            if(ri){rq.push_back({input(),clocks,delay,prior_cycle});++r_in;}
            if(bi){bq.push_back({d->b_payload_i,clocks,delay,prior_cycle});++b_in;}
            if(delay){
                if(d->r_v_o){require(!rq.empty(),"unowned R VALID");require(clocks-rq.front().accepted>=rq.front().delay,"early R offer across timestamp wrap");require(output()==rq.front().data,"R ID/data/RESP/LAST order mismatch");}
                if(d->b_v_o){require(!bq.empty(),"unowned B VALID");require(clocks-bq.front().accepted>=bq.front().delay,"early B offer");require(d->b_payload_o==bq.front().data,"B ID/RESP order mismatch");}
            }else{
                require(d->r_v_o==d->r_v_i&&d->r_ready_o==d->r_ready_i&&output()==input(),"native R wire identity lost");
                require(d->b_v_o==d->b_v_i&&d->b_ready_o==d->b_ready_i&&d->b_payload_o==d->b_payload_i,"native B wire identity lost");
            }
            if(ro){require(!rq.empty()&&output()==rq.front().data,"unexpected R acceptance");auto old=rq.front();rq.pop_front();delivered.push_back({old.accepted,clocks,old.delay,old.cycle32,prior_cycle});++r_out;}
            if(bo){require(!bq.empty()&&d->b_payload_o==bq.front().data,"unexpected B acceptance");auto old=bq.front();require(clocks-old.accepted>=old.delay,"early B acceptance");b_delivered.push_back({old.accepted,clocks,old.delay,old.cycle32,prior_cycle});bq.pop_front();++b_out;}
            held_r=d->r_v_o&&!d->r_ready_i;held_b=d->b_v_o&&!d->b_ready_i;
            held_r_data=output();held_b_data=d->b_payload_o;
            if(commit)r_stalls=b_stalls=0;
            else{
                if(delay&&d->r_v_i&&!d->r_ready_o&&r_stalls!=UINT32_MAX)++r_stalls;
                if(delay&&d->b_v_i&&!d->b_ready_o&&b_stalls!=UINT32_MAX)++b_stalls;
            }
        }else{held_r=held_b=false;r_stalls=b_stalls=0;}
        d->clk_i=1;context->time(++time);d->eval();trace->dump(time);
        uint64_t mask=(UINT64_C(1)<<d->counter_width_o)-1;
        require(d->cycle_o==(d->reset_i?uint32_t(mask-15):uint32_t((prior_cycle+UINT64_C(1))&mask)),"cycle counter progression wrong");
        if(!d->reset_i){
            require(d->r_occupancy_o==rq.size()&&d->b_occupancy_o==bq.size(),"FIFO occupancy/accounting mismatch");
            require(d->r_full_stall_cycles_o==r_stalls&&d->b_full_stall_cycles_o==b_stalls,"full-input-stall telemetry mismatch");
            max_r=std::max(max_r,unsigned(rq.size()));max_b=std::max(max_b,unsigned(bq.size()));
            uint64_t ids=0;for(const auto& entry:rq)ids|=UINT64_C(1)<<(entry.data[2]&63);
            max_ids=std::max(max_ids,unsigned(__builtin_popcountll(ids)));
        }
        d->clk_i=0;context->time(++time);d->eval();trace->dump(time);++clocks;
        require(clocks<200000,"standalone shim cycle watchdog");
    }
    void reset(){
        r_reset_drop+=rq.size();b_reset_drop+=bq.size();rq.clear();bq.clear();
        d->reset_i=1;d->r_v_i=d->b_v_i=d->cfg_v_i=0;d->r_ready_i=d->b_ready_i=0;
        for(int i=0;i<3;++i)step();d->reset_i=0;d->cfg_safe_i=1;step();
        require(d->active_delay_o==0&&!d->r_v_o&&!d->b_v_o,"reset left delayed responses");
    }
    void quiet(){d->r_v_i=d->b_v_i=0;eval();}
    void drain(){quiet();d->r_ready_i=d->b_ready_i=1;
        for(int i=0;!rq.empty()||!bq.empty();++i){require(i<20000,"response drain timeout");step();}
        step();require(d->idle_o,"queues not idle after drain");}
    void configure(unsigned n){quiet();d->cfg_safe_i=1;d->cfg_delay_i=n;d->cfg_v_i=1;eval();require(d->cfg_ready_o,"valid configuration not idle");step();
        require(d->cfg_accepted_o&&!d->cfg_error_o&&d->active_delay_o==n,"valid configuration rejected");d->cfg_v_i=0;step();}
    void native_identity(){
        reset();uint32_t random=0x52d39a17;
        for(int i=0;i<128;++i){drive(packet((uint64_t(random32(random))<<32)|random32(random),random32(random),random32(random),random32(random)&1));
            d->r_v_i=random32(random)&1;d->r_ready_i=random32(random)&1;d->b_v_i=random32(random)&1;d->b_ready_i=random32(random)&1;d->b_payload_i=uint8_t(random32(random));eval();
            require(d->r_v_o==d->r_v_i&&d->r_ready_o==d->r_ready_i&&output()==input(),"unclocked native R identity");
            require(d->b_v_o==d->b_v_i&&d->b_ready_o==d->b_ready_i&&d->b_payload_o==d->b_payload_i,"unclocked native B identity");}
        quiet();step();std::puts("AXI_DELAY_NATIVE_COMBINATIONAL_IDENTITY_PASS");
    }
    void burst(unsigned n){
        reset();configure(n);d->r_ready_i=d->b_ready_i=1;size_t begin=delivered.size(),begin_b=b_delivered.size();
        for(unsigned beat=0;beat<8;++beat){d->r_v_i=d->b_v_i=1;drive(packet(UINT64_C(0xfedcba9800000000)+beat,n==40?0:11,beat&3,beat==7));d->b_payload_i=uint8_t(beat|(beat&3)<<6);eval();
            require(d->r_ready_o&&d->b_ready_o,"configured FIFO cannot accept unit-rate burst");step();}
        drain();require(delivered.size()==begin+8,"burst response count");
        for(size_t i=begin;i<delivered.size();++i){const auto& row=delivered[i];require(row.delivered-row.accepted==n,"per-beat fixed shift differs from N");
            if(i>begin)require(row.delivered==delivered[i-1].delivered+1,"delayed burst bandwidth gap");}
        require(b_delivered.size()==begin_b+8,"B burst count mismatch");
        for(size_t i=begin_b;i<b_delivered.size();++i){const auto& row=b_delivered[i];require(row.delivered-row.accepted==n,"B fixed shift differs from N");
            if(i>begin_b)require(row.delivered==b_delivered[i-1].delivered+1,"B stream bandwidth gap");}
        auto first=delivered[begin],last=delivered.back();
        std::printf("AXI_DELAY_BURST N=%u first_added=%llu full_added=%llu output_spacing=1 B_same_N=1 input_first32=%u output_first32=%u\n",n,(unsigned long long)(first.delivered-first.accepted),(unsigned long long)(last.delivered-last.accepted),first.input32,first.output32);
    }
    void random_stream(unsigned n){
        reset();configure(n);uint32_t random=0x95a37cd1;unsigned ri=0,bi=0;bool rv=false,bv=false;size_t before=delivered.size();const unsigned count=1024;
        for(int cycles=0;ri<count||bi<count||!rq.empty()||!bq.empty();++cycles){require(cycles<40000,"random traffic timeout");
            if(!rv&&ri<count)rv=(random32(random)%100)<79;
            if(!bv&&bi<count)bv=(random32(random)%100)<71;
            d->r_v_i=rv;d->b_v_i=bv;
            if(rv)drive(packet(UINT64_C(0xd3c4b50000000000)+ri,ri%4,(ri/5)&3,(ri/4)%8==7));
            if(bv)d->b_payload_i=uint8_t((bi%64)|(((bi/7)&3)<<6));
            d->r_ready_i=(random32(random)%100)<63;d->b_ready_i=(random32(random)%100)<57;eval();
            bool ra=rv&&d->r_ready_o,ba=bv&&d->b_ready_o;step();if(ra){++ri;rv=false;}if(ba){++bi;bv=false;}
        }
        quiet();step();require(delivered.size()==before+count,"random R count mismatch");
        std::printf("AXI_DELAY_RANDOM N=%u R=%u B=%u multiID=4_PASS\n",n,ri,bi);
    }
    void full_backpressure(){
        reset();configure(std::min(40u,unsigned(d->fifo_els_o)));d->r_ready_i=d->b_ready_i=0;
        unsigned depth=d->fifo_els_o;
        for(unsigned i=0;i<depth;++i){d->r_v_i=d->b_v_i=1;drive(packet(UINT64_C(0x1234000000000000)+i,i%64,i&3,i%8==7));d->b_payload_i=uint8_t(i);eval();require(d->r_ready_o&&d->b_ready_o,"FIFO became full prematurely");step();}
        drive(packet(UINT64_C(0x5555666677778888),37,2,true));d->b_payload_i=0xe9;
        for(int i=0;i<13;++i){eval();require(d->r_full_o&&d->b_full_o&&!d->r_ready_o&&!d->b_ready_o,"full FIFO did not backpressure");step();}
        unsigned old=d->active_delay_o;d->cfg_delay_i=0;d->cfg_v_i=1;eval();require(!d->cfg_ready_o,"busy config unexpectedly ready");step();
        require(d->cfg_error_o&&!d->cfg_accepted_o&&d->active_delay_o==old,"busy config changed stream");d->cfg_v_i=0;
        require(d->r_full_stall_cycles_o>=14&&d->b_full_stall_cycles_o>=14,"full backpressure not reported");
        d->r_ready_i=d->b_ready_i=1;step();quiet();drain();
        std::printf("AXI_DELAY_FULL_QUEUE depth=%u preserved=1 reported_stall=1\n",depth);
    }
    void eligible_hold_wrap(){
        reset();configure(1);d->r_ready_i=d->b_ready_i=0;d->r_v_i=d->b_v_i=1;drive(packet(UINT64_C(0x89abcdef01234567),61,3,true));d->b_payload_i=0xc7;step();quiet();
        require(d->r_v_o&&d->b_v_o,"N1 response not eligible");
        unsigned hold=d->counter_width_o<=12?(1u<<d->counter_width_o)+32u:64u;
        for(unsigned i=0;i<hold;++i){require(d->r_v_o&&d->b_v_o,"eligible VALID fell during clock wrap/stall");step();}
        drain();std::printf("AXI_DELAY_ELIGIBLE_HOLD counter_bits=%u held_cycles=%u stable_PASS\n",d->counter_width_o,hold);
    }
    void config_and_reset(){
        reset();d->cfg_safe_i=0;d->cfg_v_i=1;d->cfg_delay_i=40;step();require(d->cfg_error_o&&!d->cfg_accepted_o&&d->active_delay_o==0,"unsafe config accepted");d->cfg_v_i=0;
        d->cfg_safe_i=1;d->cfg_v_i=1;d->cfg_delay_i=385;step();require(d->cfg_error_o&&!d->cfg_accepted_o&&d->active_delay_o==0,"out-of-range config accepted");d->cfg_v_i=0;configure(40);
        d->r_ready_i=d->b_ready_i=0;
        for(unsigned i=0;i<3;++i){d->r_v_i=d->b_v_i=1;drive(packet(i+UINT64_C(0x9999000000000000),i,0,i==2));d->b_payload_i=uint8_t(i);step();}
        require(rq.size()==3&&bq.size()==3,"reset fixture not queued");reset();native_identity();burst(1);
        std::puts("AXI_DELAY_CONFIG_DRAIN_RESET_PASS");
    }
    void checks(){
        native_identity();
        for(unsigned n:{1u,2u,8u,40u,200u,384u})if(n<=d->fifo_els_o)burst(n);
        random_stream(0);random_stream(std::min(40u,unsigned(d->fifo_els_o)));full_backpressure();eligible_hold_wrap();config_and_reset();drain();
        require(rq.empty()&&bq.empty()&&r_in==r_out+r_reset_drop&&b_in==b_out+b_reset_drop,"final response conservation mismatch");
        std::printf("AXI_DELAY_COUNTS R_in=%llu R_out=%llu R_reset_drop=%llu B_in=%llu B_out=%llu B_reset_drop=%llu peakR=%u peakB=%u queuedIDs=%u\n",(unsigned long long)r_in,(unsigned long long)r_out,(unsigned long long)r_reset_drop,(unsigned long long)b_in,(unsigned long long)b_out,(unsigned long long)b_reset_drop,max_r,max_b,max_ids);
        require(max_r==d->fifo_els_o&&max_b==d->fifo_els_o&&max_ids>=std::min(4u,unsigned(d->fifo_els_o)),"queue/concurrency coverage absent");
        std::printf("AXI_RESPONSE_DELAY_PASS FIFO=%u COUNTER=%u\n",d->fifo_els_o,d->counter_width_o);
    }
};
int main(){try{Sim sim;sim.checks();std::puts("AXI_DELAY_EXIT_CLEAN");return 0;}catch(const std::exception& error){std::fprintf(stderr,"AXI_DELAY_FAIL: %s\n",error.what());return 1;}}
