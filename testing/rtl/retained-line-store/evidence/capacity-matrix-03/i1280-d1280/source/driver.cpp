#include "Vretained_line_store_wrapper.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>

using Line = std::array<uint32_t,16>;
static void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
static uint64_t address(int lane, int ordinal) {
    return UINT64_C(0x01000000) + uint64_t(lane)*UINT64_C(0x00400000) + uint64_t(ordinal)*64;
}
static Line payload(uint64_t addr, int salt=0) {
    Line data{};
    for (int word=0;word<8;++word) {
        uint64_t value=(UINT64_C(0x13579bdf02468ace)^addr)+uint64_t(word)*UINT64_C(0x1111111111111111)+uint64_t(salt);
        data[2*word]=uint32_t(value);data[2*word+1]=uint32_t(value>>32);
    }
    return data;
}

struct Sim {
    std::unique_ptr<VerilatedContext> context{new VerilatedContext};
    std::unique_ptr<Vretained_line_store_wrapper> d{new Vretained_line_store_wrapper{context.get()}};
    std::unique_ptr<VerilatedFstC> trace{new VerilatedFstC};
    uint64_t ticks=0;
    bool skew;
    std::array<uint64_t,2> queries{},responses{},inserts{},terminals{},publications{};
    explicit Sim(bool asynchronous):skew(asynchronous) {
        context->traceEverOn(true);d->trace(trace.get(),99);trace->open("retained-line-store.fst");
        d->reset_i=3;d->clear_i=0;d->invalidate_v_i=0;d->lookup_v_i=0;d->insert_v_i=0;
        d->resp_ready_i=3;d->insert_replace_i=3;d->insert_cancel_i=0;
        d->clk_i=skew?0:2;d->eval();trace->dump(0);
        for(int i=0;i<50;++i)tick();
        fall(0);bit(d->reset_i,0,false);fall(1);bit(d->reset_i,1,false);eval();
    }
    ~Sim(){d->final();trace->close();}
    static bool on(unsigned bus,int lane){return (bus>>lane)&1u;}
    static void bit(CData& bus,int lane,bool value){bus=CData((bus&~(1u<<lane))|(unsigned(value)<<lane));}
    void eval(){d->eval();}
    void tick(){
        unsigned before=d->clk_i;uint64_t next=ticks+1;
        unsigned clocks=unsigned((next/5)&1u);
        clocks|=(skew?unsigned((next/7)&1u):1u-clocks)<<1;
        for(int lane=0;lane<2;++lane) if(!on(before,lane)&&on(clocks,lane)) {
            if(on(d->reset_i,lane)){queries[lane]=responses[lane]=inserts[lane]=terminals[lane]=publications[lane]=0;}
            else {
                if(on(d->lookup_v_i&d->lookup_ready_o,lane))++queries[lane];
                if(on(d->resp_v_o&d->resp_ready_i,lane)){
                    require(responses[lane]<queries[lane],"response without lookup");++responses[lane];
                }
                if(on(d->insert_v_i&d->insert_ready_o,lane))++inserts[lane];
                if(on(d->insert_done_o,lane)){
                    require(terminals[lane]<inserts[lane],"insert terminal without request");++terminals[lane];
                }
                if(on(d->insert_published_o,lane)){
                    require(on(d->insert_done_o,lane),"publication without terminal");++publications[lane];
                }
                if(on(d->epoch_wrap_o,lane))require(!on(d->lookup_ready_o,lane),"epoch wrap not blocking lookup");
            }
        }
        d->clk_i=CData(clocks);ticks=next;context->time(ticks);d->eval();trace->dump(ticks);
        require(ticks<20000000,"unit target-clock watchdog");
    }
    void fall(int lane){
        for(int n=0;n<30;++n){bool was=on(d->clk_i,lane);tick();if(was&&!on(d->clk_i,lane))return;}
        throw std::runtime_error("missing lane clock edge");
    }
    void ready(int lane){
        for(unsigned n=0;n<d->i_lines_o+d->d_lines_o+200;++n){if(on(d->lookup_ready_o,lane))return;fall(lane);}
        throw std::runtime_error("backend ready timeout");
    }
    void set_lookup(int lane,uint64_t addr){if(lane)d->lookup_addr1_i=addr;else d->lookup_addr0_i=addr;}
    void set_insert(int lane,uint64_t addr,const Line& data){
        if(lane){d->insert_addr1_i=addr;for(int i=0;i<16;++i)d->insert_data1_i[i]=data[i];}
        else{d->insert_addr0_i=addr;for(int i=0;i<16;++i)d->insert_data0_i[i]=data[i];}
    }
    void set_invalidate(int lane,uint64_t addr){if(lane)d->invalidate_addr1_i=addr;else d->invalidate_addr0_i=addr;}
    void query_start(int lane,uint64_t addr){
        fall(lane);ready(lane);set_lookup(lane,addr);bit(d->lookup_v_i,lane,true);eval();
        fall(lane);bit(d->lookup_v_i,lane,false);eval();
    }
    void wait_response(int lane){
        for(int n=0;n<600;++n){if(on(d->resp_v_o,lane))return;fall(lane);}
        throw std::runtime_error("lookup response timeout");
    }
    void response(int lane,bool hit,const Line& data={}){
        wait_response(lane);require(on(d->resp_hit_o,lane)==hit,"wrong lookup hit lane"+std::to_string(lane));
        if(hit)for(int i=0;i<16;++i)require((lane?d->resp_data1_o[i]:d->resp_data0_o[i])==data[i],"full64B payload mismatch");
        fall(lane);
    }
    void query(int lane,uint64_t addr,bool hit,int salt=0){query_start(lane,addr);response(lane,hit,payload(addr&~UINT64_C(63),salt));}
    void insert_start(int lane,uint64_t addr,int salt=0,bool replace=true){
        fall(lane);
        for(unsigned n=0;!on(d->insert_ready_o,lane);++n){require(n<d->i_lines_o+d->d_lines_o+200,"insert ready timeout");fall(lane);}
        set_insert(lane,addr,payload(addr,salt));bit(d->insert_replace_i,lane,replace);bit(d->insert_v_i,lane,true);eval();
        fall(lane);bit(d->insert_v_i,lane,false);eval();
    }
    void terminal(int lane,bool published){
        for(int n=0;!on(d->insert_done_o,lane);++n){require(n<600,"insert terminal timeout");fall(lane);}
        require(on(d->insert_published_o,lane)==published,"wrong insert publication");fall(lane);
    }
    void put(int lane,uint64_t addr,int salt=0,bool replace=true,bool published=true){insert_start(lane,addr,salt,replace);terminal(lane,published);}
    void invalidate(int lane,uint64_t addr){fall(lane);set_invalidate(lane,addr);bit(d->invalidate_v_i,lane,true);eval();fall(lane);bit(d->invalidate_v_i,lane,false);eval();}
    void flush(int lane){fall(lane);bit(d->clear_i,lane,true);eval();fall(lane);bit(d->clear_i,lane,false);eval();ready(lane);}
    bool writing(int lane){return on(d->debug_data_v_o&d->debug_data_w_o,lane);}
    bool reading(int lane){return on(d->debug_data_v_o,lane)&&!on(d->debug_data_w_o,lane);}
    unsigned word(int lane){return lane?d->debug_word1_o:d->debug_word0_o;}
    template<class P>void wait(int lane,P predicate){for(int n=0;!predicate();++n){require(n<600,"phase wait timeout");fall(lane);}}
    void capacity(int lane,int lines){
        ready(lane);query(lane,address(lane,0),false);
        if(!lines){put(lane,address(lane,0),0,true,false);}
        else {
            for(int n=0;n<lines;++n)put(lane,address(lane,n));
            for(int n=0;n<lines;++n)query(lane,address(lane,n)+17,true);
            int conflict=((lines+63)/64)*64;
            put(lane,address(lane,conflict),9,false,false);query(lane,address(lane,0),true);
            put(lane,address(lane,conflict),9);query(lane,address(lane,0),false);query(lane,address(lane,conflict),true,9);
            if(lines>1){put(lane,address(lane,1),31,false);query(lane,address(lane,1),true,31);}
        }
        std::printf("RETAINED_CAPACITY_CHECK lane=%d lines=%d full64B=1\n",lane,lines);
    }
    void checks(){
        capacity(0,int(d->i_lines_o));capacity(1,int(d->d_lines_o));
        for(int lane=0;lane<2;++lane)if(lane?d->d_lines_o:d->i_lines_o){
            flush(lane);uint64_t low=address(lane,0),high=low+(UINT64_C(1)<<32);
            put(lane,low,111);query(lane,high,false);put(lane,high,222);
            query(lane,high,true,222);query(lane,low,(lane?d->d_lines_o:d->i_lines_o)>64,111);
        }
        if(d->i_lines_o>=64&&d->d_lines_o>=64){
            // Both independent BRAM ports are genuinely active concurrently.
            flush(0);flush(1);ready(0);ready(1);
            insert_start(0,UINT64_C(0x3000000),101);insert_start(1,UINT64_C(0x3000000),202);
            bool overlap=false;bool done0=false,done1=false;
            for(int n=0;n<10000&&!(done0&&done1);++n){
                overlap|=writing(0)&&writing(1);
                if(on(d->insert_done_o,0)){require(on(d->insert_published_o,0),"parallel I insert dropped");done0=true;}
                if(on(d->insert_done_o,1)){require(on(d->insert_published_o,1),"parallel D insert dropped");done1=true;}
                tick();
            }
            std::printf("RETAINED_PORT_OVERLAP clock=%s observed=%u\n",skew?"different-periods":"inverted",unsigned(overlap));
            require(done0&&done1&&(skew||overlap),"inverted shared ports did not overlap real payload writes");
            for(int n=0;n<30;++n)tick();
            query(0,UINT64_C(0x3000000),true,101);query(1,UINT64_C(0x3000000),true,202);
            flush(0);put(0,address(0,1));if(d->i_lines_o>65)put(0,address(0,65));put(0,address(0,2));
            invalidate(0,address(0,1)+7);query(0,address(0,1),false);if(d->i_lines_o>65)query(0,address(0,65),false);query(0,address(0,2),true);
            query_start(0,address(0,2));wait(0,[&]{return reading(0);});
            set_invalidate(0,address(0,2));bit(d->invalidate_v_i,0,true);eval();fall(0);bit(d->invalidate_v_i,0,false);eval();response(0,false);
            put(0,address(0,3));bit(d->resp_ready_i,0,false);query_start(0,address(0,3));wait_response(0);
            require(on(d->resp_hit_o,0),"missing stalled hit");
            Line held{};for(int i=0;i<16;++i)held[i]=d->resp_data0_o[i];
            for(int n=0;n<3;++n){fall(0);require(on(d->resp_v_o&d->resp_hit_o,0),"held response changed");for(int i=0;i<16;++i)require(d->resp_data0_o[i]==held[i],"held data changed");}
            set_invalidate(0,address(0,3));bit(d->invalidate_v_i,0,true);eval();require(on(d->resp_v_o,0)&&!on(d->resp_hit_o,0),"queued hit not immediately revoked");
            fall(0);bit(d->invalidate_v_i,0,false);eval();fall(0);require(on(d->resp_v_o,0)&&!on(d->resp_hit_o,0),"revoked response lost");
            bit(d->resp_ready_i,0,true);eval();response(0,false);
            insert_start(0,address(0,4));wait(0,[&]{return writing(0);});fall(0);bit(d->insert_cancel_i,0,true);eval();fall(0);bit(d->insert_cancel_i,0,false);eval();terminal(0,false);query(0,address(0,4),false);
            insert_start(0,address(0,5));wait(0,[&]{return writing(0)&&word(0)==7;});
            set_invalidate(0,address(0,5));bit(d->invalidate_v_i,0,true);eval();fall(0);bit(d->invalidate_v_i,0,false);eval();terminal(0,false);query(0,address(0,5),false);
            put(0,address(0,6));query_start(0,address(0,6));bit(d->clear_i,0,true);eval();fall(0);bit(d->clear_i,0,false);eval();response(0,false);ready(0);query(0,address(0,6),false);
            insert_start(0,address(0,7));wait(0,[&]{return writing(0);});bit(d->clear_i,0,true);eval();fall(0);bit(d->clear_i,0,false);eval();terminal(0,false);ready(0);query(0,address(0,7),false);
            flush(1);put(1,address(1,8));put(1,address(1,9));for(int n=0;n<3;++n)invalidate(1,address(1,8));query(1,address(1,9),true);
            bit(d->resp_ready_i,1,false);query_start(1,address(1,9));wait_response(1);require(on(d->resp_hit_o,1),"prewrap hit absent");
            set_invalidate(1,address(1,8));bit(d->invalidate_v_i,1,true);eval();require(!on(d->resp_hit_o,1),"wrap failed to revoke other-set hit");fall(1);require(on(d->epoch_wrap_o,1),"missing epoch wrap pulse");
            bit(d->invalidate_v_i,1,false);bit(d->resp_ready_i,1,true);eval();response(1,false);ready(1);query(1,address(1,8),false);query(1,address(1,9),false);put(1,address(1,8),77);query(1,address(1,8),true,77);
        }
        for(int n=0;n<30;++n)tick();
        for(int lane=0;lane<2;++lane){
            require(queries[lane]==responses[lane],"missing/extra lookup responses");require(inserts[lane]==terminals[lane],"missing/extra insert terminals");
            std::printf("RETAINED_COUNTS lane=%d queries=%llu responses=%llu inserts=%llu terminals=%llu published=%llu\n",lane,(unsigned long long)queries[lane],(unsigned long long)responses[lane],(unsigned long long)inserts[lane],(unsigned long long)terminals[lane],(unsigned long long)publications[lane]);
        }
        std::printf("RETAINED_LINE_STORE_PASS I=%u D=%u clock=%s\n",d->i_lines_o,d->d_lines_o,skew?"different-periods":"inverted");
    }
};
int main(int argc,char**argv){
    bool skew=argc==2&&std::string(argv[1])=="different-periods";
    if(argc>2||(argc==2&&!skew))return 2;
    try{Sim sim(skew);sim.checks();std::puts("RETAINED_TEST_EXIT_CLEAN");return 0;}
    catch(const std::exception& error){std::fprintf(stderr,"RETAINED_TEST_FAIL: %s\n",error.what());return 1;}
}
