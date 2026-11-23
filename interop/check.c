// Calls the kernels' native static library from C and prints, as JSON, the
// value per BPT after each exit of the batch on each kernel, and the check
// each kernel fails, for scripts/harness/native.py to compare with the EVM.
//
//   cc interop/check.c libkernels.a -o check && ./check
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

// The functions interop/kernels.fe exports, as Fe's native backend builds them.
uint32_t exits(void);
uint64_t value_after(uint32_t kernel, uint32_t n);
uint32_t failure(uint32_t kernel);

static double now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
  static const char *names[] = {"faithful", "typed", "guarded"};
  double started = now_ms();
  uint32_t count = exits();
  printf("{\"exits\": %" PRIu32 ", \"kernels\": {", count);
  for (uint32_t kernel = 0; kernel < 3; kernel++) {
    printf("%s\"%s\": {\"values\": [", kernel ? ", " : "", names[kernel]);
    for (uint32_t n = 0; n <= count; n++) {
      uint64_t value = value_after(kernel, n);
      if (value == 0) break;
      printf("%s\"%" PRIu64 "\"", n ? ", " : "", value);
    }
    uint32_t code = failure(kernel);
    if (code == UINT32_MAX) printf("], \"failure\": null}");
    else printf("], \"failure\": %" PRIu32 "}", code);
  }
  printf("}, \"milliseconds\": %.0f}\n", now_ms() - started);
  return 0;
}
