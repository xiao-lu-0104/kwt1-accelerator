#ifndef KWT_ENCODER_H
#define KWT_ENCODER_H
#include <stddef.h>
#include <stdint.h>

#define KWT_ENCODER_BASE ((uintptr_t)0x40000000u)
#define KWT_INPUT_BYTES 6336u
#define KWT_LAYER_WORDS 7564u
#define KWT_LAYERS 12u
#define KWT_CTRL 0x0000u
#define KWT_STATUS 0x0004u
#define KWT_CORE_CYCLES 0x0008u
#define KWT_TASK_CYCLES 0x000cu
#define KWT_INPUT_WORDS 0x0010u
#define KWT_PARAM_WORDS 0x0014u
#define KWT_OUTPUT_BYTES 0x0018u
#define KWT_READ_WORDS 0x001cu
#define KWT_REQUEST 0x0020u
#define KWT_SIGNATURE 0x0024u
#define KWT_PARAM_DATA 0x0030u
#define KWT_INPUT 0x1000u
#define KWT_OUTPUT 0x4000u
#define KWT_BUSY 1u
#define KWT_DONE 2u
#define KWT_ERROR 4u
#define KWT_PARAM_READY 8u

enum { KWT_OK=0, KWT_EINVAL=-1, KWT_EDEVICE=-2, KWT_ETIMEOUT=-3, KWT_ELOAD=-4 };
struct kwt_metrics {
    uint32_t core_cycles;
    uint32_t peripheral_cycles; /* Diagnostic window; excludes CPU result stores. */
    uint64_t cpu_cycles;        /* Includes input, parameter callback and output copy. */
    int cpu_cycles_valid;
};
/* Fill the caller-owned single-layer scratch buffer, low/high words in order.
 * Return 0 on success; do not allocate all model parameters inside the driver. */
typedef int (*kwt_load_layer_fn)(void *context, unsigned layer, uint32_t *words, size_t count);
int kwt_encoder_run(uintptr_t base, const int8_t *input, int8_t *output,
                    uint32_t *layer_scratch, size_t scratch_words,
                    kwt_load_layer_fn load_layer, void *context,
                    unsigned max_polls, struct kwt_metrics *metrics);
#endif
