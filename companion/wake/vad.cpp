// SPDX-License-Identifier: MIT
// Local-only second-stage speech verification. No ASR, network or recordings.
#include "whisper.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

static void quiet(enum ggml_log_level, const char *, void *) {}
int main(int argc, char **argv) {
    if (argc != 3 || std::string(argv[1]) != "--model") return 2;
    whisper_log_set(quiet, nullptr);
    auto params = whisper_vad_default_context_params();
    params.n_threads = 2;
    params.use_gpu = false;
    auto *ctx = whisper_vad_init_from_file_with_params(argv[2], params);
    if (!ctx) return 3;
    std::cout << "{\"ready\":true}" << std::endl;
    while (true) {
        unsigned char header[4];
        if (!std::cin.read(reinterpret_cast<char *>(header), 4)) break;
        const uint32_t n = uint32_t(header[0]) | uint32_t(header[1]) << 8 |
                           uint32_t(header[2]) << 16 | uint32_t(header[3]) << 24;
        if (n < 4000 || n > 800000) break;
        std::vector<unsigned char> raw(n*2);
        if (!std::cin.read(reinterpret_cast<char *>(raw.data()), raw.size())) break;
        std::vector<float> pcm(n);
        for (uint32_t i = 0; i < n; ++i)
            pcm[i] = static_cast<int16_t>(uint16_t(raw[2*i]) | uint16_t(raw[2*i+1]) << 8) / 32768.0f;
        const auto started = std::chrono::steady_clock::now();
        if (!whisper_vad_detect_speech(ctx, pcm.data(), n)) break;
        // Silero's 512-sample windows at 16 kHz. Use the upstream 0.5 speech
        // threshold and require 256 ms, matching its 250 ms minimum duration.
        const int count = whisper_vad_n_probs(ctx);
        const float *probs = whisper_vad_probs(ctx);
        int run = 0, longest = 0, voiced = 0;
        bool valid = count > 0 && probs;
        for (int i = 0; valid && i < count; ++i) {
            valid = std::isfinite(probs[i]) && probs[i] >= 0 && probs[i] <= 1;
            if (probs[i] >= 0.5f) { ++run; ++voiced; } else run = 0;
            longest = std::max(longest, run);
        }
        if (!valid) break;
        const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-started).count();
        std::cout << "{\"accepted\":" << (longest >= 8 ? "true" : "false")
                  << ",\"speech_ms\":" << voiced*32 << ",\"max_run_ms\":" << longest*32
                  << ",\"milliseconds\":" << ms << "}" << std::endl;
    }
    whisper_vad_free(ctx);
    return 0;
}
