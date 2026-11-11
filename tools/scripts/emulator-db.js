/**
 * MATRIXHUNT ULTIMATE - Emulator Requirements Database
 * License: CC BY-NC-SA 4.0
 * Author: Arkadiusz Slowik
 *
 * 21 platforms from NES to PS5
 * GPU scores: 0-100 based on WebGL renderer detection
 */

const EMULATOR_DB = {
    // === 8-bit / 16-bit (FULL SPEED na prawie sprzecie) ===
    nes: {
        name: "NES",
        fullName: "Nintendo Entertainment System",
        emulator: "RetroArch (FCEUmm / Nestopia)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1983",
        note: null
    },
    snes: {
        name: "SNES",
        fullName: "Super Nintendo Entertainment System",
        emulator: "RetroArch (Snes9x / bsnes)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1990",
        note: null
    },
    gb: {
        name: "Game Boy",
        fullName: "Nintendo Game Boy",
        emulator: "RetroArch (Gambatte)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1989",
        note: null
    },
    gbc: {
        name: "Game Boy Color",
        fullName: "Nintendo Game Boy Color",
        emulator: "RetroArch (Gambatte)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1998",
        note: null
    },
    gba: {
        name: "GBA",
        fullName: "Game Boy Advance",
        emulator: "RetroArch (mGBA / VBA-M)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "2001",
        note: null
    },
    genesis: {
        name: "Genesis/Mega Drive",
        fullName: "Sega Genesis / Mega Drive",
        emulator: "RetroArch (Genesis Plus GX)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1988",
        note: null
    },
    neogeo: {
        name: "Neo Geo",
        fullName: "SNK Neo Geo AES/MVS",
        emulator: "RetroArch (FBNeo)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1990",
        note: null
    },
    atari2600: {
        name: "Atari 2600",
        fullName: "Atari 2600",
        emulator: "RetroArch (Stella)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1977",
        note: null
    },
    c64: {
        name: "Commodore 64",
        fullName: "Commodore 64",
        emulator: "RetroArch (VICE)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1982",
        note: null
    },
    arcade: {
        name: "Arcade (MAME)",
        fullName: "Arcade (MAME/FBNeo)",
        emulator: "MAME / RetroArch FBNeo",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 2,
        vulkan: false,
        tier: "retro",
        year: "1978+",
        note: null
    },
    pce: {
        name: "PC Engine",
        fullName: "NEC PC Engine / TurboGrafx-16",
        emulator: "RetroArch (Mednafen PCE)",
        minGPU: "Intel HD 3000",
        minCPUcores: 1,
        minRAM: 1,
        vulkan: false,
        tier: "retro",
        year: "1987",
        note: null
    },

    // === 32/64-bit (lekko wymagajace) ===
    ps1: {
        name: "PS1",
        fullName: "Sony PlayStation 1",
        emulator: "DuckStation / Beetle PSX",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 2,
        vulkan: false,
        tier: "light",
        year: "1994",
        note: null
    },
    n64: {
        name: "N64",
        fullName: "Nintendo 64",
        emulator: "Mupen64Plus / Parallel",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 2,
        vulkan: false,
        tier: "light",
        year: "1996",
        note: null
    },
    dreamcast: {
        name: "Dreamcast",
        fullName: "Sega Dreamcast",
        emulator: "Flycast",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 2,
        vulkan: false,
        tier: "light",
        year: "1998",
        note: null
    },
    psp: {
        name: "PSP",
        fullName: "PlayStation Portable",
        emulator: "PPSSPP",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 4,
        vulkan: false,
        tier: "light",
        year: "2004",
        note: null
    },
    nds: {
        name: "Nintendo DS",
        fullName: "Nintendo DS",
        emulator: "RetroArch (melonDS / DeSmuME)",
        minGPU: "Intel HD 4000",
        minCPUcores: 2,
        minRAM: 2,
        vulkan: false,
        tier: "light",
        year: "2004",
        note: null
    },

    // === 64-bit (wymagajace) ===
    ps2: {
        name: "PS2",
        fullName: "Sony PlayStation 2",
        emulator: "PCSX2",
        minGPU: "GTX 1050",
        minCPUcores: 4,
        minRAM: 8,
        vulkan: true,
        tier: "medium",
        year: "2000",
        note: null
    },
    gamecube: {
        name: "GameCube",
        fullName: "Nintendo GameCube",
        emulator: "Dolphin",
        minGPU: "GTX 1050",
        minCPUcores: 4,
        minRAM: 8,
        vulkan: true,
        tier: "medium",
        year: "2001",
        note: null
    },
    wii: {
        name: "Wii",
        fullName: "Nintendo Wii",
        emulator: "Dolphin",
        minGPU: "GTX 1050",
        minCPUcores: 4,
        minRAM: 8,
        vulkan: true,
        tier: "medium",
        year: "2006",
        note: null
    },
    ds3: {
        name: "3DS",
        fullName: "Nintendo 3DS",
        emulator: "Lime3DS (Citra fork)",
        minGPU: "GTX 1050",
        minCPUcores: 4,
        minRAM: 8,
        vulkan: true,
        tier: "medium",
        year: "2011",
        note: null
    },
    xbox: {
        name: "Xbox",
        fullName: "Microsoft Xbox",
        emulator: "Xemu",
        minGPU: "GTX 1060",
        minCPUcores: 4,
        minRAM: 8,
        vulkan: true,
        tier: "medium",
        year: "2001",
        note: null
    },

    // === NOWE GENERACJE (bardzo wymagajace) ===
    wiiu: {
        name: "Wii U",
        fullName: "Nintendo Wii U",
        emulator: "Cemu",
        minGPU: "GTX 1060",
        minCPUcores: 6,
        minRAM: 16,
        vulkan: true,
        tier: "high",
        year: "2012",
        note: null
    },
    switch: {
        name: "Switch",
        fullName: "Nintendo Switch",
        emulator: "Sudachi / Yuzu successor",
        minGPU: "GTX 1660",
        minCPUcores: 6,
        minRAM: 16,
        vulkan: true,
        tier: "high",
        year: "2017",
        note: null
    },
    ps3: {
        name: "PS3",
        fullName: "Sony PlayStation 3",
        emulator: "RPCS3",
        minGPU: "GTX 1660",
        minCPUcores: 6,
        minRAM: 16,
        vulkan: true,
        tier: "high",
        year: "2006",
        note: "6+ cores strongly recommended"
    },

    // === NEXT-GEN (ekstremalnie wymagajace) ===
    ps4: {
        name: "PS4",
        fullName: "Sony PlayStation 4",
        emulator: "shadPS4",
        minGPU: "RTX 2060",
        minCPUcores: 8,
        minRAM: 16,
        vulkan: true,
        tier: "ultra",
        year: "2013",
        note: "111 playable games (v0.16.0+). Requires firmware dump from PS4 console."
    },
    ps5: {
        name: "PS5",
        fullName: "Sony PlayStation 5",
        emulator: "KytyPS5 / SharpEmu",
        minGPU: "RTX 3070",
        minCPUcores: 8,
        minRAM: 32,
        vulkan: true,
        tier: "experimental",
        year: "2020",
        note: "EARLY STAGE. Few games playable. Requires high-end hardware."
    }
};

// GPU score lookup: maps substring matches to numeric scores 0-100
const GPU_SCORES = [
    // NVIDIA RTX 50xx (next-gen)
    ['5090', 100], ['5080', 98], ['5070', 95], ['5060', 90],
    // NVIDIA RTX 40xx
    ['4090', 100], ['4080', 95], ['4070 ti super', 93], ['4070 super', 88],
    ['4070', 85], ['4060 ti', 82], ['4060', 78],
    // NVIDIA RTX 30xx
    ['3090 ti', 92], ['3090', 90], ['3080 ti', 88], ['3080', 85],
    ['3070 ti', 82], ['3070', 78], ['3060 ti', 72], ['3060', 68],
    // 30xx laptop cards were missing entirely and fell through to the
    // blanket "rtx -> 60" fallback, so an RTX 3050 laptop scored exactly
    // like a desktop 3080. The 3050 is the most common laptop GPU there is.
    ['3050 ti', 52], ['3050', 48], ['3050 laptop', 48],
    // NVIDIA RTX 20xx
    ['2080 ti', 78], ['2080 super', 76], ['2080', 74],
    ['2070 super', 70], ['2070', 68], ['2060 super', 65], ['2060', 62],
    // NVIDIA GTX 16xx
    ['1660 ti', 58], ['1660 super', 56], ['1660', 54],
    ['1650 super', 48], ['1650', 44],
    // NVIDIA GTX 10xx
    ['1080 ti', 58], ['1080', 54], ['1070 ti', 52], ['1070', 50],
    ['1060', 44], ['1050 ti', 36], ['1050', 30],
    // Intel Arc — MUST come before the GTX 7xx block below. getGPUScore
    // returns the FIRST substring hit, so ['770', 24] up there also matched
    // "arc a770" and scored a 16-TFLOP discrete card below a GTX 750 Ti.
    ['arc b580', 58], ['arc a770', 60], ['arc a750', 54], ['arc a580', 48],
    ['arc a380', 32],
    // NVIDIA GTX 9xx
    ['980 ti', 40], ['980', 36], ['970', 34], ['960', 28], ['950', 24],
    // NVIDIA GTX 7xx
    ['780 ti', 28], ['780', 26], ['770', 24], ['760', 22], ['750 ti', 20], ['750', 18],
    // AMD RX 9000
    ['9070 xt', 90], ['9070', 85],
    // AMD RX 7000
    ['7900 xtx', 95], ['7900 xt', 92], ['7900 gre', 88],
    ['7800 xt', 82], ['7700 xt', 76], ['7600 xt', 68], ['7600', 64],
    // AMD RX 6000
    ['6950 xt', 85], ['6900 xt', 82], ['6800 xt', 78], ['6800', 74],
    ['6750 xt', 70], ['6700 xt', 66], ['6700', 62],
    ['6650 xt', 58], ['6600 xt', 54], ['6600', 50],
    ['6500 xt', 34], ['6400', 28],
    // AMD RX 5000
    ['5700 xt', 56], ['5700', 52], ['5600 xt', 48], ['5500 xt', 40],
    // AMD RX Vega
    ['vega 64', 42], ['vega 56', 38],
    // AMD R9
    ['r9 390x', 30], ['r9 390', 28], ['r9 380', 24], ['r9 280', 22],
    // Intel Integrated
    ['uhd 770', 22], ['uhd 750', 18], ['uhd 730', 15], ['uhd 630', 12],
    ['uhd 620', 10], ['uhd 615', 8], ['uhd 610', 7], ['uhd 605', 6],
    ['hd 530', 11], ['hd 520', 10], ['hd 4600', 9], ['hd 4400', 8],
    ['hd 4000', 7], ['hd 3000', 5], ['hd 2500', 3],
    // Apple
    ['apple m4 max', 85], ['apple m4 pro', 75], ['apple m4', 65],
    ['apple m3 max', 80], ['apple m3 pro', 70], ['apple m3', 60],
    ['apple m2 max', 72], ['apple m2 pro', 62], ['apple m2', 52],
    ['apple m1 max', 65], ['apple m1 pro', 55], ['apple m1', 45],
];

// GPU score lookup function
function getGPUScore(renderer) {
    if (!renderer) return 5;
    // Real WebGL strings are "Intel(R) UHD Graphics 630", "AMD Radeon(TM)
    // Graphics" etc. The table keys on "uhd 630", so the word "graphics"
    // sitting in the middle meant every integrated-GPU row was dead code and
    // they all fell through to the flat fallback of 10. Normalise once.
    const r = renderer.toLowerCase()
        .replace(/\(r\)|\(tm\)|\(®\)|\(™\)/g, ' ')
        .replace(/\bgraphics\b/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    // Longest matching pattern wins, NOT the first one in the table. The
    // table is a flat list, so ['770', 24] (GTX 770) shadowed ['uhd 770', 22]
    // and scored an Intel UHD 770 as a 2010-era Fermi card. Sorting by
    // pattern length makes every specific row beat every generic one,
    // regardless of the order they happen to be written in.
    let best = null;
    for (const [pattern, score] of GPU_SCORES) {
        if (r.includes(pattern) && (!best || pattern.length > best[0].length)) {
            best = [pattern, score];
        }
    }
    if (best) return best[1];
    // Fallback heuristics
    if (r.includes('rtx')) return 60;
    if (r.includes('gtx')) return 40;
    if (r.includes('radeon') && r.includes('rx')) return 40;
    if (r.includes('radeon') && (r.includes('vega') || r.includes('r9'))) return 30;
    if (r.includes('intel') && r.includes('arc')) return 40;
    if (r.includes('uhd') || r.includes('hd graphics')) return 10;
    if (r.includes('mali') || r.includes('adreno')) return 15;
    return 5;
}

// Emulator requirements: GPU score thresholds for each tier.
// "slow" is the floor BELOW which a machine is unfit. It used to be 0 for
// retro and 2 for light, which made the `else` branch of the GPU ladder
// unreachable for 16 of 26 platforms: every machine, including one with no
// WebGL at all (gpuScore 0), still collected 12/40 GPU points and "NES"
// came out as PLAYABLE on hardware that cannot run it.
const EMU_TIERS = {
    retro:     { full: 5,  mostly: 3,  playable: 1,  slow: -1 },
    light:     { full: 15, mostly: 10, playable: 5,  slow: -1 },
    medium:    { full: 50, mostly: 40, playable: 30, slow: 20 },
    high:      { full: 65, mostly: 55, playable: 45, slow: 35 },
    ultra:     { full: 80, mostly: 70, playable: 60, slow: 45 },
    experimental: { full: 95, mostly: 85, playable: 75, slow: 60 }
};

// CPU core requirements for each tier
const CPU_TIERS = {
    retro:     1,
    light:     2,
    medium:    4,
    high:      6,
    ultra:     8,
    experimental: 8
};

// RAM requirements (GB) for each tier
const RAM_TIERS = {
    retro:     1,
    light:     2,
    medium:    8,
    high:      16,
    ultra:     16,
    experimental: 32
};

/**
 * Read a numeric hardware value, accepting either the nested shape returned by
 * HardwareDetector.detectAll() ({gpu:{score},cpu:{cores},ram:{gb},vulkan:{supported}})
 * or the flat shape used by the preset profiles ({gpuScore,cpuCores,ramGB,vulkanSupported}).
 */
/**
 * Per-entry hardware floor, resolved from minGPU / minCPUcores / minRAM.
 *
 * Those three fields were declared on all 26 entries and consulted by nobody,
 * so the requirements the UI showed were fiction. minGPU is a renderer name
 * ("Intel HD Graphics 4000"), so it is resolved through the same lookup as the
 * user's own card, which keeps the two consistent.
 */
const _floor_cache = new Map();

function _entryFloor(emu) {
    const hit = _floor_cache.get(emu);
    if (hit) return hit;

    const floor = {
        gpu: typeof getGPUScore === 'function' && emu.minGPU
            ? getGPUScore(emu.minGPU) : 0,
        cores: Number.isFinite(emu.minCPUcores) ? emu.minCPUcores : 0,
        ram: Number.isFinite(emu.minRAM) ? emu.minRAM : 0,
    };
    _floor_cache.set(emu, floor);
    return floor;
}

function readHw(hw, nestedKey, flatKey, subKey, fallback = 0) {
    if (!hw) return fallback;
    if (hw[nestedKey] && typeof hw[nestedKey][subKey] === 'number') {
        return hw[nestedKey][subKey];
    }
    if (typeof hw[flatKey] === 'number') {
        return hw[flatKey];
    }
    return fallback;
}

/**
 * Score an emulator against detected hardware
 * @param {Object} emu - Emulator entry from EMULATOR_DB
 * @param {Object} hw - Detected hardware (nested detectAll() shape or flat preset shape)
 * @returns {number} Score 0-100
 */
function scoreEmulator(emu, hw) {
    let score = 0;

    const gpuScore = readHw(hw, 'gpu', 'gpuScore', 'score', 0);
    const cpuCores = readHw(hw, 'cpu', 'cpuCores', 'cores', 0);
    const ramGB = readHw(hw, 'ram', 'ramGB', 'gb', 0);
    const vulkanSupported = !!(hw && hw.vulkan && typeof hw.vulkan.supported === 'boolean'
        ? hw.vulkan.supported
        : hw && hw.vulkanSupported);

    // navigator.deviceMemory is spec-capped (Chromium reports at most 8) and
    // is absent outside Chrome/Edge entirely, which readHw surfaces as 0.
    // Scoring 0 punishes the user for our inability to read the value, and it
    // also made the 16/32 GB tiers unreachable: RAM contributes proportionally
    // to its own budget, so an unknown value is dropped from the denominator
    // instead of counting as a failure.
    const ramKnown = ramGB > 0;

    // GPU scoring (40 points max)
    const tierThresholds = EMU_TIERS[emu.tier] || EMU_TIERS.medium;
    if (gpuScore >= tierThresholds.full) score += 40;
    else if (gpuScore >= tierThresholds.mostly) score += 32;
    else if (gpuScore >= tierThresholds.playable) score += 22;
    else if (gpuScore >= tierThresholds.slow) score += 12;
    else score += Math.min(gpuScore, 5);

    // minGPU / minCPUcores / minRAM were declared on all 26 entries and read
    // by nothing, and some contradicted the tier tables: `arcade` declared
    // "Intel HD 4000" but sat in the retro tier whose GPU "full" is 5 (= HD
    // 3000). Now that a per-entry floor is actually consulted, a machine below
    // it cannot be reported as FULL SPEED for that title.
    const floor = _entryFloor(emu);

    // CPU scoring (30 points max)
    const minCPU = Math.max(CPU_TIERS[emu.tier] || 4, floor.cores);
    if (cpuCores >= minCPU * 2) score += 30;
    else if (cpuCores >= minCPU * 1.5) score += 25;
    else if (cpuCores >= minCPU) score += 20;
    else if (cpuCores >= minCPU * 0.75) score += 12;
    else score += Math.min(cpuCores * 3, 8);

    // RAM scoring (20 points max, only when we could actually read it)
    if (ramKnown) {
        const minRAM = Math.max(RAM_TIERS[emu.tier] || 8, floor.ram);
        if (ramGB >= minRAM * 4) score += 20;
        else if (ramGB >= minRAM * 2) score += 18;
        else if (ramGB >= minRAM) score += 14;
        else if (ramGB >= minRAM * 0.5) score += 8;
        else score += Math.min(ramGB * 2, 5);
    } else {
        // Unknown: assume the middle of the band rather than zero. Scoring 0
        // punished the user for our inability to read the value and made
        // "SNES = SLOW" appear on capable hardware in Firefox and Safari.
        // 14 is the "meets the minimum" award, so an unread RAM cost is
        // indistinguishable from having exactly enough of it.
        score += 14;
    }

    // Vulkan bonus (10 points)
    if (emu.vulkan && vulkanSupported) score += 10;
    else if (emu.vulkan && !vulkanSupported) score -= 15;

    // Hard floor from the entry's own requirement. A machine below minGPU
    // cannot be "full speed" for that title regardless of how the tier
    // ladder scored it, so cap the result.
    if (gpuScore < floor.gpu || cpuCores < floor.cores) {
        score = Math.min(score, 20);
    } else if (ramKnown && ramGB < floor.ram) {
        score = Math.min(score, 45);
    }

    return Math.min(Math.max(score, 0), 100);
}

/**
 * Get human-readable status from score
 */
function getScoreStatus(score) {
    if (score >= 90) return { text: "FULL SPEED", color: "var(--ok)", icon: "FULL" };
    if (score >= 75) return { text: "MOSTLY FULL", color: "var(--mid)", icon: "GOOD" };
    if (score >= 55) return { text: "PLAYABLE", color: "var(--mid)", icon: "OK" };
    if (score >= 35) return { text: "SLOW", color: "var(--warn)", icon: "SLOW" };
    if (score >= 15) return { text: "BARELY", color: "var(--warn)", icon: "WEAK" };
    return { text: "NOT PLAYABLE", color: "var(--bad)", icon: "NO" };
}

/**
 * Get tier display label
 */
function getTierLabel(tier) {
    const labels = {
        retro: "8/16-BIT",
        light: "32/64-BIT",
        medium: "6TH GEN",
        high: "7TH GEN",
        ultra: "8TH GEN",
        experimental: "NEXT-GEN"
    };
    return labels[tier] || tier.toUpperCase();
}

/**
 * Preset hardware profiles for "what if" scenarios
 */
const PRESET_PROFILES = {
    potato: {
        name: "POTATO",
        desc: "Intel HD + i3 + 4GB",
        icon: "P",
        hw: { gpuScore: 8, cpuCores: 2, ramGB: 4, vulkanSupported: false },
        settings: { renderer: "OpenGL", resolution: "1x native", shaders: "none", vsync: "OFF" }
    },
    balanced: {
        name: "BALANCED",
        desc: "GTX 1050 Ti + i5-8400 + 8GB",
        icon: "B",
        hw: { gpuScore: 36, cpuCores: 6, ramGB: 8, vulkanSupported: true },
        settings: { renderer: "Vulkan", resolution: "1x native", shaders: "CRT-Royale (retro)", vsync: "ON" }
    },
    performance: {
        name: "PERFORMANCE",
        desc: "RTX 2060 + Ryzen 5 3600 + 16GB",
        icon: "G",
        hw: { gpuScore: 62, cpuCores: 6, ramGB: 16, vulkanSupported: true },
        settings: { renderer: "Vulkan", resolution: "2x native", shaders: "CRT-Royale + FXAA", vsync: "ON" }
    },
    overkill: {
        name: "OVERKILL",
        desc: "RTX 4070 + i7-13700K + 32GB",
        icon: "O",
        hw: { gpuScore: 85, cpuCores: 16, ramGB: 32, vulkanSupported: true },
        settings: { renderer: "Vulkan", resolution: "4x native + AA", shaders: "All shaders ON", vsync: "ON 144Hz" }
    }
};
