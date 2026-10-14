// Inspect raw 2D ASTC with the unmodified ARM astcenc 5.7.0 public API.
// No pixel-color heuristic is used. Exit 0: all blocks LDR; 2: HDR/error block;
// 1: invalid input or inspector failure. JSON is emitted for inspected images.
#include "astcenc.h"
#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>

static unsigned u24(const uint8_t* p) {
    return p[0] | (unsigned(p[1]) << 8) | (unsigned(p[2]) << 16);
}

static void require_api(astcenc_error status) {
    if (status != ASTCENC_SUCCESS) {
        throw std::runtime_error(astcenc_get_error_string(status));
    }
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: astc-block-info image.astc");
        std::ifstream input(argv[1], std::ios::binary | std::ios::ate);
        if (!input) throw std::runtime_error("cannot open ASTC file");
        auto length = input.tellg();
        if (length < 16 || length > 256 * 1024 * 1024) {
            throw std::runtime_error("ASTC file size outside bounds");
        }
        std::vector<uint8_t> bytes(static_cast<size_t>(length));
        input.seekg(0);
        if (!input.read(reinterpret_cast<char*>(bytes.data()), length)) {
            throw std::runtime_error("cannot read complete ASTC file");
        }
        if (bytes[0] != 0x13 || bytes[1] != 0xab || bytes[2] != 0xa1 || bytes[3] != 0x5c) {
            throw std::runtime_error("invalid raw ASTC magic");
        }
        unsigned bx = bytes[4], by = bytes[5], bz = bytes[6];
        unsigned width = u24(bytes.data() + 7), height = u24(bytes.data() + 10);
        unsigned depth = u24(bytes.data() + 13);
        if (!bx || !by || bz != 1 || depth != 1 || !width || !height ||
            width > 16384 || height > 16384 || uint64_t(width) * height > 64 * 1024 * 1024) {
            throw std::runtime_error("only bounded nonempty 2D ASTC is supported");
        }
        size_t nx = (width + bx - 1) / bx;
        size_t ny = (height + by - 1) / by;
        size_t blocks = nx * ny;
        if (bytes.size() != 16 + blocks * 16) {
            throw std::runtime_error("ASTC payload size mismatch");
        }
        astcenc_config config;
        // HDR profile preserves HDR endpoint-mode information. In an LDR context,
        // unpack_color_endpoints replaces unsupported HDR endpoints with errors.
        require_api(astcenc_config_init(ASTCENC_PRF_HDR, bx, by, 1,
                    ASTCENC_PRE_FASTEST, ASTCENC_FLG_DECOMPRESS_ONLY, &config));
        astcenc_context* raw_context = nullptr;
        require_api(astcenc_context_alloc(&config, 1, &raw_context, nullptr));
        std::unique_ptr<astcenc_context, decltype(&astcenc_context_free)>
            context(raw_context, astcenc_context_free);
        size_t hdr = 0, errors = 0, constant_ldr = 0, constant_hdr = 0;
        std::array<size_t, 16> endpoint_modes {};
        std::vector<std::string> examples;
        for (size_t i = 0; i < blocks; ++i) {
            const uint8_t* block = bytes.data() + 16 + i * 16;
            astcenc_block_info info;
            require_api(astcenc_get_block_info(context.get(), block, &info));
            // ARM 5.7.0 returns early for valid constant blocks, leaving is_hdr_block
            // zero. Only AFTER the library validates a constant block, inspect the
            // one dynamic-range bit defined by ASTC C.2.23 (bit 9 of the block).
            bool is_hdr = !info.is_error_block && (info.is_constant_block
                ? bool(block[1] & 2) : info.is_hdr_block);
            if (info.is_error_block) ++errors;
            else if (is_hdr) ++hdr;
            if (info.is_constant_block) {
                if (is_hdr) ++constant_hdr;
                else ++constant_ldr;
            }
            if (!info.is_error_block && !info.is_constant_block) {
                for (unsigned p = 0; p < info.partition_count; ++p) {
                    ++endpoint_modes.at(info.color_endpoint_modes[p]);
                }
            }
            if ((is_hdr || info.is_error_block) && examples.size() < 16) {
                std::ostringstream item;
                item << "{\"block_index\":" << i << ",\"raw_astc_offset\":" << 16 + i * 16
                     << ",\"block_x\":" << i % nx << ",\"block_y\":" << i / nx
                     << ",\"classification\":\"" << (info.is_error_block ? "error" : "hdr")
                     << "\",\"constant\":" << (info.is_constant_block ? "true" : "false")
                     << ",\"hex\":\"";
                for (unsigned j = 0; j < 16; ++j) {
                    item << std::hex << std::setfill('0') << std::setw(2) << unsigned(block[j]);
                }
                item << "\"}";
                examples.push_back(item.str());
            }
        }
        std::cout << "{\"format_version\":1,\"astcenc_version\":\"5.7.0\","
                  << "\"inspection_profile\":\"HDR\",\"width\":" << width
                  << ",\"height\":" << height << ",\"block\":[" << bx << ',' << by
                  << "],\"block_count\":" << blocks << ",\"ldr_blocks\":" << blocks - hdr - errors
                  << ",\"hdr_blocks\":" << hdr << ",\"error_blocks\":" << errors
                  << ",\"constant_ldr_blocks\":" << constant_ldr
                  << ",\"constant_hdr_blocks\":" << constant_hdr
                  << ",\"ldr_compatible\":" << ((!hdr && !errors) ? "true" : "false")
                  << ",\"endpoint_mode_partition_counts\":[";
        for (size_t i = 0; i < endpoint_modes.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << endpoint_modes[i];
        }
        std::cout << "],\"first_problem_blocks\":[";
        for (size_t i = 0; i < examples.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << examples[i];
        }
        std::cout << "]}\n";
        return (hdr || errors) ? 2 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
