#include "Encoder.h"
#include "Tpu.h"
#include "SharedLayout.h"

// Mailbox words: ready sequence, released sequence, done, error,
// task kind (0 encoder / 1 FF1), layer count, fractions, boot-ready.
static volatile uint32_t *const Mail = (volatile uint32_t *)TPU_MAILBOX;

static int WaitDma(void) {
    uint32_t Status;
    do {
        Status = TpuStatus(0);
        if (Status & 0x30) return -1;
    } while (Status & 2);
    return 0;
}

void Main(void) {
    Mail[7] = 1;
    while (Mail[0] == 0) { }
    uint32_t Kind = Mail[4], Layers = Mail[5];
    if (Kind > 1 || Layers == 0 || Layers > 12 || (Kind == 1 && Layers != 1)) goto Failed;
    if (Kind == 1) {
        if (TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, TPU_OUTPUT, Mail[6])) goto Failed;
        Mail[1] = 1;
    } else {
        TpuStatus(0x3c);
        TpuLoad(TPU_INPUT, 0, 0);
        if (WaitDma()) goto Failed;
        for (uint32_t Layer = 0; Layer < Layers; ++Layer) {
            while (Mail[0] != Layer + 1) { }
            __asm__ volatile ("fence rw, rw" ::: "memory");
            TpuLayerParams Params = {
                TPU_PARAMETERS + TPU_PARAM_QUERY, TPU_PARAMETERS + TPU_PARAM_KEY,
                TPU_PARAMETERS + TPU_PARAM_VALUE, TPU_PARAMETERS + TPU_PARAM_OUTPUT,
                TPU_PARAMETERS + TPU_PARAM_NORM1, TPU_PARAMETERS + TPU_PARAM_FF1,
                TPU_PARAMETERS + TPU_PARAM_FF2, TPU_PARAMETERS + TPU_PARAM_NORM2, Mail[6]
            };
            if (TpuRunLayer(&Params)) goto Failed;
            __asm__ volatile ("fence rw, rw" ::: "memory");
            Mail[1] = Layer + 1;
        }
        TpuStore(TPU_OUTPUT, 0, 0);
        if (WaitDma()) goto Failed;
    }
    __asm__ volatile ("fence rw, rw" ::: "memory");
    Mail[2] = 1;
    return;
Failed:
    Mail[3] = TpuStatus(0);
    Mail[2] = 2;
}
