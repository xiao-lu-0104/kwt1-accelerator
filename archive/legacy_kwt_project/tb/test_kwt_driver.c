/* Host control-flow model only; numerical/AXI/CPU validation is separate. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "kwt_encoder.h"
static uint32_t device_read(uintptr_t address);
static void device_write(uintptr_t address,uint32_t value);
#define KWT_MMIO_READ32(address) device_read(address)
#define KWT_MMIO_WRITE32(address,value) device_write(address,value)
#include "../sw/kwt_encoder.c"

static uint8_t input_memory[KWT_INPUT_BYTES];
static unsigned input_words,param_words,read_words,status_reads,resets,loads;
static int phase,mode;
static uint32_t device_read(uintptr_t address)
{
    unsigned offset=(unsigned)(address-KWT_ENCODER_BASE),i;
    if(offset==KWT_SIGNATURE) return mode==4?0:0x4b575431u;
    if(offset==KWT_STATUS) {
        status_reads++;
        if(mode==2 && param_words>=10) return KWT_ERROR|KWT_BUSY;
        if(phase==3) return KWT_DONE;
        if(phase==2) return KWT_BUSY|((mode!=1 && status_reads%3)?KWT_PARAM_READY:0);
        return 0;
    }
    if(offset==KWT_CORE_CYCLES) return 0x12345678u;
    if(offset==KWT_TASK_CYCLES) return 0x23456789u;
    assert(phase==3 && offset==KWT_OUTPUT+4*read_words && read_words<KWT_INPUT_BYTES/4);
    i=4*read_words++;
    return (uint32_t)(input_memory[i]^0x5a)|((uint32_t)(input_memory[i+1]^0x5a)<<8)|
           ((uint32_t)(input_memory[i+2]^0x5a)<<16)|((uint32_t)(input_memory[i+3]^0x5a)<<24);
}
static void device_write(uintptr_t address,uint32_t value)
{
    unsigned offset=(unsigned)(address-KWT_ENCODER_BASE),i;
    if(offset==KWT_CTRL) {
        if(value==2) {phase=1;input_words=0;param_words=0;read_words=0;resets++;}
        else {assert(value==1 && phase==1 && input_words==KWT_INPUT_BYTES/4);phase=2;}
    } else if(offset==KWT_PARAM_DATA) {
        assert(phase==2 && param_words<KWT_LAYERS*KWT_LAYER_WORDS);
        assert(value==0x10000000u+(param_words/KWT_LAYER_WORDS)*10000+param_words%KWT_LAYER_WORDS);
        if(++param_words==KWT_LAYERS*KWT_LAYER_WORDS) phase=3;
    } else {
        assert(phase==1 && offset==KWT_INPUT+4*input_words && input_words<KWT_INPUT_BYTES/4);
        i=4*input_words++;
        input_memory[i]=(uint8_t)value;input_memory[i+1]=(uint8_t)(value>>8);
        input_memory[i+2]=(uint8_t)(value>>16);input_memory[i+3]=(uint8_t)(value>>24);
    }
}
static int load_layer(void *context,unsigned layer,uint32_t *words,size_t count)
{
    size_t i;
    (void)context;
    assert(count==KWT_LAYER_WORDS && layer==loads);
    loads++;
    if(mode==3 && layer==2) return -1;
    for(i=0;i<count;i++) words[i]=0x10000000u+layer*10000+(unsigned)i;
    return 0;
}
int main(void)
{
    static int8_t input[KWT_INPUT_BYTES],output[KWT_INPUT_BYTES];
    static uint32_t scratch[KWT_LAYER_WORDS];
    struct kwt_metrics metrics;
    unsigned i,round,prior;
    for(i=0;i<KWT_INPUT_BYTES;i++) input[i]=(int8_t)(uint8_t)(i*17);
    for(round=0;round<2;round++) {
        loads=0;mode=0;
        assert(kwt_encoder_run(KWT_ENCODER_BASE,input,output,scratch,KWT_LAYER_WORDS,load_layer,0,8,&metrics)==KWT_OK);
        assert(loads==12 && param_words==90768 && read_words==1584);
        assert(metrics.core_cycles==0x12345678u && metrics.peripheral_cycles==0x23456789u && !metrics.cpu_cycles_valid);
        for(i=0;i<KWT_INPUT_BYTES;i++) assert((uint8_t)output[i]==((uint8_t)input[i]^0x5a));
    }
    for(mode=1;mode<=3;mode++) {
        int expected=mode==1?KWT_ETIMEOUT:mode==2?KWT_EDEVICE:KWT_ELOAD;
        loads=0;prior=resets;
        assert(kwt_encoder_run(KWT_ENCODER_BASE,input,output,scratch,KWT_LAYER_WORDS,load_layer,0,8,0)==expected);
        assert(resets==prior+2 && phase==1 && param_words==0);
    }
    mode=4;prior=resets;loads=0;
    assert(kwt_encoder_run(KWT_ENCODER_BASE,input,output,scratch,KWT_LAYER_WORDS,load_layer,0,8,0)==KWT_EDEVICE);
    assert(resets==prior && loads==0);
    assert(kwt_encoder_run(KWT_ENCODER_BASE,input,output,scratch,1,load_layer,0,8,0)==KWT_EINVAL);
    assert(kwt_encoder_run(KWT_ENCODER_BASE,input,output,scratch,KWT_LAYER_WORDS,load_layer,0,0,0)==KWT_EINVAL);
    puts("PASS: C driver input/parameters/output, layer callback, two tasks, polling, errors, timeout and abort reset");
    return 0;
}
