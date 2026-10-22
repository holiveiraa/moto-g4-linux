// SPDX-License-Identifier: MIT
// Local-only persistent recognizer. No networking, forced phrase, audio logs,
// model downloads or transcript files. Parent owns capture and activation policy.
#include "whisper.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

static void quiet(enum ggml_log_level, const char *, void *) {}
static std::string quoted(const std::string &s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (c < 32) out += ' ';
        else out += c;
    }
    return out + '"';
}
int main(int argc, char **argv) {
    if (argc != 3 || std::string(argv[1]) != "--model") return 2;
    whisper_log_set(quiet, nullptr);
    auto cp = whisper_context_default_params();
    cp.use_gpu = false;
    auto *ctx = whisper_init_from_file_with_params(argv[2], cp);
    if (!ctx) return 3;
    std::cout << "{\"ready\":true}" << std::endl;
    while (true) {
        // Bounded little-endian sample count followed by mono 16 kHz S16_LE.
        unsigned char header[4];
        if (!std::cin.read(reinterpret_cast<char *>(header), 4)) break;
        const uint32_t n = uint32_t(header[0]) | uint32_t(header[1]) << 8 |
                           uint32_t(header[2]) << 16 | uint32_t(header[3]) << 24;
        if (n < 4000 || n > 160000) break;
        std::vector<unsigned char> raw(n * 2);
        if (!std::cin.read(reinterpret_cast<char *>(raw.data()), raw.size())) break;
        std::vector<float> pcm(n);
        for (uint32_t i = 0; i < n; ++i)
            pcm[i] = static_cast<int16_t>(uint16_t(raw[2*i]) | uint16_t(raw[2*i+1]) << 8) / 32768.0f;
        auto p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
        p.n_threads = 4;
        p.language = "pt";
        p.translate = false;
        p.no_context = true;
        p.no_timestamps = true;
        p.single_segment = true;
        p.print_progress = false;
        p.print_realtime = false;
        p.print_timestamps = false;
        p.print_special = false;
        p.audio_ctx = 384;
        p.max_tokens = 20;
        p.temperature = 0.0f;
        p.temperature_inc = 0.0f;
        const auto started = std::chrono::steady_clock::now();
        if (whisper_full(ctx, p, pcm.data(), n) != 0) break;
        std::string text;
        double probability = 0, no_speech = 1;
        int tokens = 0;
        for (int i = 0; i < whisper_full_n_segments(ctx); ++i) {
            text += whisper_full_get_segment_text(ctx, i);
            no_speech = std::min(no_speech, double(whisper_full_get_segment_no_speech_prob(ctx, i)));
            for (int j = 0; j < whisper_full_n_tokens(ctx, i); ++j) {
                if (whisper_full_get_token_id(ctx, i, j) >= whisper_token_eot(ctx)) continue;
                probability += whisper_full_get_token_p(ctx, i, j);
                ++tokens;
            }
        }
        probability = tokens ? probability/tokens : 0;
        const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-started).count();
        if (!std::isfinite(probability) || !std::isfinite(no_speech)) break;
        std::cout << "{\"text\":" << quoted(text) << ",\"probability\":" << probability
                  << ",\"no_speech\":" << no_speech << ",\"milliseconds\":" << ms << "}" << std::endl;
    }
    whisper_free(ctx);
    return 0;
}
