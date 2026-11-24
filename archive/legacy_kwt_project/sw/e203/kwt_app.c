/* Actual E203 application. Images preload the two platform TCMs, as for ISA
 * tests; all accelerator input/parameter/output movement is performed by CPU. */
#include "kwt_encoder.h"
#include "kwt_e203_layout.h"

#ifndef KWT_CPU_SMOKE
static int load_layer(void *context, unsigned layer, uint32_t *words, size_t count)
{
    const volatile uint32_t *source;
    size_t i;
    (void)context;
    if(layer>=KWT_LAYERS || count!=KWT_LAYER_WORDS) return -1;
    source=(const volatile uint32_t *)(layer<KWT_SPLIT_LAYERS ?
        KWT_PARAM_A+layer*KWT_LAYER_WORDS*4u :
        KWT_PARAM_B+(layer-KWT_SPLIT_LAYERS)*KWT_LAYER_WORDS*4u);
    for(i=0;i<count;i++) words[i]=source[i];
    return 0;
}
#endif

int main(void)
{
    volatile uint32_t *mailbox=(volatile uint32_t *)KWT_MAILBOX;
#ifdef KWT_CPU_SMOKE
    volatile uint32_t *device=(volatile uint32_t *)KWT_ENCODER_BASE;
    unsigned i;
    int result=0;
    for(i=0;i<7;i++) mailbox[i]=0;
    if(device[KWT_SIGNATURE/4]!=0x4b575431u) result=-10;
    device[KWT_CTRL/4]=2;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    device[KWT_INPUT/4]=0x03020100;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    if(device[KWT_INPUT_WORDS/4]!=1) result=-11;
    device[KWT_CTRL/4]=2;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    if(device[KWT_INPUT_WORDS/4]!=0) result=-12;
    mailbox[1]=(uint32_t)result;
#else
    struct kwt_metrics metrics;
    int result;
    mailbox[0]=0;
    result=kwt_encoder_run(KWT_ENCODER_BASE,(const int8_t *)KWT_INPUT_BUFFER,
        (int8_t *)KWT_OUTPUT_BUFFER,(uint32_t *)KWT_SCRATCH,KWT_LAYER_WORDS,
        load_layer,0,1000000u,&metrics);
    mailbox[1]=(uint32_t)result;
    mailbox[2]=metrics.core_cycles;
    mailbox[3]=metrics.peripheral_cycles;
    mailbox[4]=(uint32_t)metrics.cpu_cycles;
    mailbox[5]=(uint32_t)(metrics.cpu_cycles>>32);
    mailbox[6]=(uint32_t)metrics.cpu_cycles_valid;
#endif
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    mailbox[0]=result==KWT_OK?0x4b57544fu:0x4b575446u;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    for(;;) __asm__ volatile ("nop");
}
