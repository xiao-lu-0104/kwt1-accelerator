#include "kwt_encoder.h"

#ifndef KWT_MMIO_READ32
#define KWT_MMIO_READ32(address) (*(volatile uint32_t *)(address))
#endif
#ifndef KWT_MMIO_WRITE32
#define KWT_MMIO_WRITE32(address, value) (*(volatile uint32_t *)(address)=(value))
#endif

static void io_fence(void)
{
#if defined(__riscv)
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#elif defined(__GNUC__)
    __asm__ volatile ("" ::: "memory");
#endif
}
static uint32_t read_reg(uintptr_t base, unsigned offset)
{
    uint32_t value;
    io_fence();
    value=KWT_MMIO_READ32(base+offset);
    io_fence();
    return value;
}
static void write_reg(uintptr_t base, unsigned offset, uint32_t value)
{
    io_fence();
    KWT_MMIO_WRITE32(base+offset,value);
    io_fence();
}
static uint64_t cpu_cycle_count(void)
{
#if defined(__riscv) && __riscv_xlen == 32
    uint32_t hi,lo,again;
    do {
        __asm__ volatile ("csrr %0, mcycleh" : "=r"(hi) :: "memory");
        __asm__ volatile ("csrr %0, mcycle" : "=r"(lo) :: "memory");
        __asm__ volatile ("csrr %0, mcycleh" : "=r"(again) :: "memory");
    } while(hi!=again);
    return ((uint64_t)hi<<32)|lo;
#elif defined(__riscv)
    uint64_t value;
    __asm__ volatile ("csrr %0, mcycle" : "=r"(value) :: "memory");
    return value;
#else
    return 0;
#endif
}
static int wait_flag(uintptr_t base, unsigned flag, unsigned limit)
{
    unsigned i;
    for(i=0;i<limit;i++) {
        uint32_t status=read_reg(base,KWT_STATUS);
        if(status & KWT_ERROR) return KWT_EDEVICE;
        if(status & flag) return KWT_OK;
    }
    return KWT_ETIMEOUT;
}
int kwt_encoder_run(uintptr_t base, const int8_t *input, int8_t *output,
                    uint32_t *layer_scratch, size_t scratch_words,
                    kwt_load_layer_fn load_layer, void *context,
                    unsigned max_polls, struct kwt_metrics *metrics)
{
    unsigned i,layer;
    uint64_t begin,end;
    int result;
    if(!input || !output || !layer_scratch || !load_layer ||
       scratch_words<KWT_LAYER_WORDS || !max_polls || (base & 0xffffu)) return KWT_EINVAL;
    if(metrics) {metrics->core_cycles=0;metrics->peripheral_cycles=0;metrics->cpu_cycles=0;metrics->cpu_cycles_valid=0;}
    if(read_reg(base,KWT_SIGNATURE)!=0x4b575431u) return KWT_EDEVICE;
    write_reg(base,KWT_CTRL,2u);
    begin=cpu_cycle_count();
    for(i=0;i<KWT_INPUT_BYTES;i+=4) {
        uint32_t word=(uint8_t)input[i] | ((uint32_t)(uint8_t)input[i+1]<<8) |
                      ((uint32_t)(uint8_t)input[i+2]<<16) | ((uint32_t)(uint8_t)input[i+3]<<24);
        write_reg(base,KWT_INPUT+i,word);
    }
    write_reg(base,KWT_CTRL,1u);
    for(layer=0;layer<KWT_LAYERS;layer++) {
        if(load_layer(context,layer,layer_scratch,KWT_LAYER_WORDS)!=0) {result=KWT_ELOAD;goto abort;}
        for(i=0;i<KWT_LAYER_WORDS;i++) {
            result=wait_flag(base,KWT_PARAM_READY,max_polls);
            if(result!=KWT_OK) goto abort;
            write_reg(base,KWT_PARAM_DATA,layer_scratch[i]);
        }
    }
    result=wait_flag(base,KWT_DONE,max_polls);
    if(result!=KWT_OK) goto abort;
    for(i=0;i<KWT_INPUT_BYTES;i+=4) {
        uint32_t word=read_reg(base,KWT_OUTPUT+i);
        output[i]=(int8_t)(uint8_t)word;
        output[i+1]=(int8_t)(uint8_t)(word>>8);
        output[i+2]=(int8_t)(uint8_t)(word>>16);
        output[i+3]=(int8_t)(uint8_t)(word>>24);
    }
    io_fence();end=cpu_cycle_count();
    if(metrics) {
        metrics->core_cycles=read_reg(base,KWT_CORE_CYCLES);
        metrics->peripheral_cycles=read_reg(base,KWT_TASK_CYCLES);
        metrics->cpu_cycles=end-begin;
#if defined(__riscv)
        metrics->cpu_cycles_valid=1;
#endif
    }
    return KWT_OK;
abort:
    write_reg(base,KWT_CTRL,2u);
    return result;
}
