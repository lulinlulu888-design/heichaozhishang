// Decode exactly four SHA-256-pinned original clips with unmodified ACL v1.2.0.
// ACL 1.2.0 is_valid() is not a full internal-layout validator. No unrecognized
// bytes reach that decoder; this is intentionally not a general ACL importer.
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <acl/algorithm/uniformly_sampled/decoder.h>
#include <acl/core/ansi_allocator.h>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool value, const char* reason) {
    if (!value) throw std::runtime_error(reason);
}
static uint32_t u32(const uint8_t* p) { uint32_t v; std::memcpy(&v, p, 4); return v; }
static uint16_t u16(const uint8_t* p) { uint16_t v; std::memcpy(&v, p, 2); return v; }

static std::string hex(const uint8_t* data, size_t size) {
    constexpr char alphabet[] = "0123456789abcdef";
    std::string result(size * 2, '0');
    for (size_t i = 0; i < size; ++i) {
        result[i * 2] = alphabet[data[i] >> 4];
        result[i * 2 + 1] = alphabet[data[i] & 15];
    }
    return result;
}

static std::string sha256(const uint8_t* data, size_t size) {
    struct Handles {
        BCRYPT_ALG_HANDLE algorithm = nullptr;
        BCRYPT_HASH_HANDLE hash = nullptr;
        ~Handles() {
            if (hash) BCryptDestroyHash(hash);
            if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
        }
    } handles;
    require(BCryptOpenAlgorithmProvider(&handles.algorithm, BCRYPT_SHA256_ALGORITHM,
        nullptr, 0) >= 0, "cannot initialize SHA-256");
    DWORD objectSize = 0, received = 0;
    require(BCryptGetProperty(handles.algorithm, BCRYPT_OBJECT_LENGTH,
        reinterpret_cast<PUCHAR>(&objectSize), sizeof(objectSize), &received, 0) >= 0 &&
        received == sizeof(objectSize), "cannot query SHA-256 storage");
    std::vector<uint8_t> object(objectSize);
    // Explicitly destroy the hash before the backing object goes out of scope.
    require(BCryptCreateHash(handles.algorithm, &handles.hash, object.data(),
        objectSize, nullptr, 0, 0) >= 0, "cannot create SHA-256 hash");
    std::array<uint8_t, 32> digest{};
    const bool hashed = size <= std::numeric_limits<ULONG>::max() &&
        BCryptHashData(handles.hash, const_cast<PUCHAR>(data), ULONG(size), 0) >= 0 &&
        BCryptFinishHash(handles.hash, digest.data(), ULONG(digest.size()), 0) >= 0;
    BCryptDestroyHash(handles.hash);
    handles.hash = nullptr;
    require(hashed, "SHA-256 computation failed");
    return hex(digest.data(), digest.size());
}

// Keep the temporary handle open exclusively through all writes. Publication is
// a same-directory Windows rename after flush/close, with no copy fallback.
class AtomicOutput {
    std::filesystem::path destination, temporary;
    HANDLE handle = INVALID_HANDLE_VALUE;
public:
    explicit AtomicOutput(const std::filesystem::path& path) : destination(path) {
        for (unsigned attempt = 0; attempt < 8; ++attempt) {
            std::array<uint8_t, 16> random{};
            require(BCryptGenRandom(nullptr, random.data(), ULONG(random.size()),
                BCRYPT_USE_SYSTEM_PREFERRED_RNG) >= 0, "temporary filename generation failed");
            const auto suffix = hex(random.data(), random.size());
            const auto candidate = destination.parent_path() /
                (L".acl-sample-" + std::wstring(suffix.begin(), suffix.end()) + L".tmp");
            handle = CreateFileW(candidate.c_str(), GENERIC_WRITE, 0, nullptr,
                CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (handle != INVALID_HANDLE_VALUE) { temporary = candidate; return; }
            require(GetLastError() == ERROR_FILE_EXISTS || GetLastError() == ERROR_ALREADY_EXISTS,
                "cannot create temporary output");
        }
        throw std::runtime_error("cannot allocate unique temporary output");
    }
    AtomicOutput(const AtomicOutput&) = delete;
    AtomicOutput& operator=(const AtomicOutput&) = delete;
    ~AtomicOutput() {
        if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle);
        if (!temporary.empty()) DeleteFileW(temporary.c_str());
    }
    void write(const void* data, size_t count) {
        DWORD written = 0;
        require(count <= MAXDWORD && WriteFile(handle, data, DWORD(count), &written, nullptr) &&
            written == count, "temporary output write failed");
    }
    void publish() {
        require(FlushFileBuffers(handle) != 0, "temporary output flush failed");
        const HANDLE closing = handle;
        handle = INVALID_HANDLE_VALUE;
        require(CloseHandle(closing) != 0, "temporary output close failed");
        require(MoveFileExW(temporary.c_str(), destination.c_str(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0,
            "atomic output replacement failed");
        temporary.clear();
    }
};

struct Writer : acl::OutputWriter {
    std::vector<float> pose;
    explicit Writer(size_t bones) : pose(bones * 10) {}
    void write_bone_rotation(uint16_t i, const acl::Quat_32& q) {
        float* p = pose.data() + i * 10;
        p[0] = acl::quat_get_x(q); p[1] = acl::quat_get_y(q);
        p[2] = acl::quat_get_z(q); p[3] = acl::quat_get_w(q);
    }
    void write_bone_translation(uint16_t i, const acl::Vector4_32& v) {
        float* p = pose.data() + i * 10 + 4;
        p[0] = acl::vector_get_x(v); p[1] = acl::vector_get_y(v); p[2] = acl::vector_get_z(v);
    }
    void write_bone_scale(uint16_t i, const acl::Vector4_32& v) {
        float* p = pose.data() + i * 10 + 7;
        p[0] = acl::vector_get_x(v); p[1] = acl::vector_get_y(v); p[2] = acl::vector_get_z(v);
    }
};

int wmain(int argc, wchar_t** argv) {
    try {
        require(argc == 3, "usage: acl-sample input.acl output.poses");
        const auto inputPath = std::filesystem::absolute(argv[1]).lexically_normal();
        const auto outputPath = std::filesystem::absolute(argv[2]).lexically_normal();
        require(!std::filesystem::exists(outputPath) ||
            !std::filesystem::equivalent(inputPath, outputPath),
            "input and output refer to the same file");
        std::ifstream input(inputPath, std::ios::binary | std::ios::ate);
        require(bool(input), "cannot open input");
        const auto length = input.tellg();
        require(length >= 48 && length <= 32 * 1024 * 1024, "input size outside bounds");
        const size_t size = size_t(length);
        acl::ANSIAllocator allocator;
        void* memory = allocator.allocate(size + 64, 64);
        require(memory != nullptr, "input allocation failed");
        std::memset(memory, 0, size + 64); // Library SIMD reads may touch padding.
        struct Release { acl::ANSIAllocator& allocator; void* ptr; size_t size;
            ~Release() { allocator.deallocate(ptr, size); } } release{allocator, memory, size + 64};
        input.seekg(0); input.read(static_cast<char*>(memory), size);
        require(bool(input), "truncated input");
        const auto* raw = static_cast<uint8_t*>(memory);
        const std::string inputHash = sha256(raw, size);
        const char* clipName = nullptr;
        if (inputHash == "cda4d69e000276ee263a47d5531c43cbc6ae84ff6e133d64fbeeb7ccb7de898f")
            clipName = "stand_idle.acl";
        if (inputHash == "6bf93b1e7791dd6124a6e13c26538cfeac56d65c0d49abffc68a818c06be4cbd")
            clipName = "skin.acl";
        if (inputHash == "26de4e5657227f27f19f64dc2c91aefe1dc5c23face79af10cb8811d5bc88a3f")
            clipName = "tutorial_enemy_idle.acl";
        if (inputHash == "7615d852c5356a2dd11f2c2e7fc04953e21a71bb5364e245fafaa8de4decbfbc")
            clipName = "tutorial_enemy_fire.acl";
        require(clipName != nullptr,
            "unsupported ACL SHA-256: only four pinned original clips are accepted");
        require(u32(raw) == size, "ACL declared size differs from payload");
        const auto& clip = *static_cast<const acl::CompressedClip*>(memory);
        const auto valid = clip.is_valid(true);
        require(valid.empty(), valid.c_str());
        const auto& h = acl::get_clip_header(clip);
        require(h.num_bones > 0 && h.num_bones <= 256 && h.num_samples > 0 &&
            h.num_samples <= 100000 && uint64_t(h.num_bones) * h.num_samples <= 2000000,
            "sample count outside output budget");
        require(std::isfinite(h.sample_rate) && h.sample_rate > 0 && h.sample_rate <= 1000,
            "invalid sample rate");
        // Additional sanity checks for the pinned clips, NOT a complete layout
        // validator. The cryptographic allowlist above is the decoder boundary.
        require(raw[20] == 4 && raw[21] == 3 && raw[22] == 3 &&
            raw[23] == 7 && raw[24] == 7 && raw[25] == 1 && raw[26] <= 1,
            "unsupported ACL track/range format");
        const auto fits = [size](uint64_t offset, uint64_t count) {
            return offset <= size && count <= size - offset;
        };
        const uint64_t segments = 16 + u16(raw + 36);
        require(h.num_segments > 0 && h.num_segments <= h.num_samples &&
            fits(segments, uint64_t(h.num_segments) * 20), "segment table outside payload");
        const uint64_t bitset = ((uint64_t(h.num_bones) * 3 + 31) / 32) * 4;
        require(fits(16 + u16(raw + 38), bitset) && fits(16 + u16(raw + 40), bitset),
            "track bitsets outside payload");
        for (int offset : {42, 44}) require(u16(raw + offset) == 0xffff ||
            fits(16 + u16(raw + offset), 1), "clip data offset outside payload");
        uint64_t samples = 0;
        for (uint32_t i = 0; i < h.num_segments; ++i) {
            const uint8_t* s = raw + segments + i * 20;
            const uint32_t n = u32(s), bits = u32(s + 4);
            require(n > 0 && n <= h.num_samples, "invalid segment sample count");
            samples += n;
            for (int field : {8, 12, 16}) require(u32(s + field) == 0xffffffff ||
                fits(16ull + u32(s + field), 1), "segment data offset outside payload");
            if (bits) require(u32(s + 16) != 0xffffffff &&
                fits(16ull + u32(s + 16), (uint64_t(bits) * n + 7) / 8),
                "segment bitstream exceeds payload");
        }
        require(samples == h.num_samples, "segment samples do not cover clip");
        acl::uniformly_sampled::DecompressionContext<acl::uniformly_sampled::DecompressionSettings> context;
        context.initialize(clip);
        Writer writer(h.num_bones);
        AtomicOutput output(outputPath);
        // HCZPOSE1 + uint32 bones + uint32 frames + float sample rate;
        // each frame: each bone quaternion xyzw, translation xyz, scale xyz.
        output.write("HCZPOSE1", 8);
        uint32_t bones = h.num_bones, frames = h.num_samples;
        output.write(reinterpret_cast<char*>(&bones), 4);
        output.write(reinterpret_cast<char*>(&frames), 4);
        output.write(reinterpret_cast<const char*>(&h.sample_rate), 4);
        float maxQuaternionError = 0;
        for (uint32_t frame = 0; frame < h.num_samples; ++frame) {
            context.seek(float(frame) / h.sample_rate, acl::SampleRoundingPolicy::Nearest);
            context.decompress_pose(writer);
            for (float v : writer.pose) require(std::isfinite(v), "nonfinite decoded transform");
            for (uint32_t i = 0; i < bones; ++i) {
                const float* q = writer.pose.data() + i * 10;
                float error = std::abs(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3] - 1);
                if (error > maxQuaternionError) maxQuaternionError = error;
                require(error < 0.001f, "decoded quaternion is not unit length");
            }
            output.write(reinterpret_cast<char*>(writer.pose.data()), writer.pose.size() * sizeof(float));
        }
        output.publish();
        std::cout << "{\"aclVersion\":\"1.2.0\",\"binaryVersion\":4,\"hashVerified\":true,\"bones\":"
            << bones << ",\"samples\":" << frames << ",\"sampleRate\":" << h.sample_rate
            << ",\"maxQuaternionError\":" << maxQuaternionError
            << ",\"validationScope\":\"sha256-pinned-original-clips-only\",\"inputSha256\":\""
            << inputHash << "\",\"clipName\":\"" << clipName << "\"}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
