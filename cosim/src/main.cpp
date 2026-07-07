
#include "bsg_argparse.h"
#include "bsg_zynq_pl.h"

#include <stdio.h>
#include <string>

extern int ps_main(bsg_zynq_pl *zpl, int argc, char **argv);

#ifdef HAS_COSIM_MAIN
extern "C" int cosim_main(char *argstr) {
#else
int main(int argc, char **argv) {
    char argstr[1025] = {0};
    get_argstr(argstr, argc, argv);
#endif
    // parse the new argc and argv from the argstr
    int ps_argc = get_argc(argstr);
    char *ps_argv[ps_argc];
    get_argv(argstr, ps_argv);

    // this ensures that even with tee, the output is line buffered
    // so that we can see what is happening in real time
    setvbuf(stdout, NULL, _IOLBF, 0);

    // Verilator needs the original argv so $value$plusargs sees simulator args
    // like +bsg_trace=..., while ps_main still consumes the filtered +c_args payload.
    bsg_zynq_pl zpl(argc, argv);
    int rc = ps_main(&zpl, ps_argc, ps_argv);
    bsg_pr_info("Returning from ps_main with RC: %x\n", rc);
    if (!rc) {
        bsg_pr_info("BSG PASS\n");
    } else {
        bsg_pr_info("BSG FAIL\n");
    }

    return rc;
}
