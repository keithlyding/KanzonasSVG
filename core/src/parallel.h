// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Running independent work (rows of a picture, color layers) on several cores.
 *
 * KZ_THREADS=N in the environment sets how many (1: everything on the calling thread, as the
 * battery does to check that the parallel result is the same, byte for byte).
 */
#ifndef KANZONASSVG_PARALLEL_H
#define KANZONASSVG_PARALLEL_H

#include <algorithm>
#include <cstdlib>
#include <exception>
#include <mutex>
#include <thread>
#include <vector>

namespace kz {

inline int threads()
{
    if (char const *e = std::getenv("KZ_THREADS")) {
        return std::clamp(std::atoi(e), 1, 64);
    }
    static int const n = std::clamp((int)std::thread::hardware_concurrency(), 1, 8);
    return n;
}

/**
 * f(begin, end) over [0, n), split into about equal parts on up to threads() threads (each
 * part at least <min_part> long). The first exception thrown is rethrown here, after every
 * part has finished.
 */
template <class F>
void parallel_for(long n, F &&f, long min_part = 32)
{
    int t = (int)std::min<long>(threads(), std::max<long>(1, n / std::max(1L, min_part)));
    if (t <= 1) {
        f(0L, n);
        return;
    }
    long const part = (n + t - 1) / t;
    std::exception_ptr error;
    std::mutex m;
    auto run = [&](long b, long e) {
        try {
            f(b, e);
        } catch (...) {
            std::lock_guard<std::mutex> lock(m);
            if (!error) {
                error = std::current_exception();
            }
        }
    };
    std::vector<std::thread> pool;
    for (int i = 1; i < t; i++) {
        long b = i * part, e = std::min(n, b + part);
        if (b >= e) {
            break;
        }
        pool.emplace_back(run, b, e);
    }
    run(0, std::min(n, part));
    for (auto &th : pool) {
        th.join();
    }
    if (error) {
        std::rethrow_exception(error);
    }
}

} // namespace kz

#endif
