"""Audio track synthesizer for ClipNova AI / PeakCut.
Generates 10 pristine, royalty-free, viral background music tracks and meme sounds
using NumPy audio synthesis and FFmpeg encoding.
"""
import math
import os
import subprocess
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf

OUT_DIR = Path("web/audio")
SR = 44100


def save_mp3(mono_or_stereo: np.ndarray, name: str, sr: int = SR, bitrate: str = "192k") -> Path:
    """Normalizes, writes WAV, and converts to MP3 in OUT_DIR."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(mono_or_stereo, dtype=np.float32)
    # Ensure 2 channels
    if audio.ndim == 1:
        audio = np.column_stack([audio, audio])
    elif audio.ndim == 2 and audio.shape[0] == 2:
        audio = audio.T
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.92

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = Path(tf.name)
    try:
        sf.write(str(wav_path), audio, sr)
        mp3_path = OUT_DIR / f"{name}.mp3"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path), "-b:a", bitrate, str(mp3_path)]
        subprocess.run(cmd, check=True)
        return mp3_path
    finally:
        wav_path.unlink(missing_ok=True)


def gen_vine_boom():
    """Iconic deep sub-bass cinematic impact with sub rumble and transient burst."""
    dur = 2.8
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    # Pitch drops from 105 Hz to 28 Hz
    freq = 28 + 77 * np.exp(-5.0 * t)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sub = np.sin(phase)
    # Saturate sub
    sub = np.tanh(3.0 * sub)
    # Attack transient burst
    transient = np.random.normal(0, 0.5, len(t)) * np.exp(-40.0 * t)
    # Rumble tail
    rumble = np.random.normal(0, 0.15, len(t)) * np.exp(-2.5 * t)
    # Envelope
    env = np.exp(-1.4 * t)
    mono = (sub * 0.85 + transient * 0.45 + rumble * 0.2) * env
    # Stereo width
    delay = int(SR * 0.016)
    left = mono
    right = np.pad(mono, (delay, 0))[:len(mono)]
    save_mp3(np.column_stack([left, right]), "vine_boom")
    print("✓ vine_boom.mp3 ready")


def gen_bruh_sound():
    """Vocal formant drop mimicking classic 'Bruh' reaction."""
    dur = 1.2
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    # Fundamental pitch contour 135 Hz down to 75 Hz
    f0 = 75 + 60 * np.exp(-3.5 * t)
    p0 = 2 * np.pi * np.cumsum(f0) / SR
    buzz = (np.sin(p0) + 0.5 * np.sin(2 * p0) + 0.3 * np.sin(3 * p0) + 0.2 * np.sin(4 * p0))
    # Formant resonances for 'Uh' (F1 ~ 450Hz, F2 ~ 850Hz)
    f1 = np.sin(2 * np.pi * (450 - 50 * t) * t) * np.exp(-3 * t)
    f2 = np.sin(2 * np.pi * (850 - 150 * t) * t) * np.exp(-3 * t)
    env = np.sin(np.pi * np.clip(t / 0.9, 0, 1)) ** 0.6
    mono = (buzz * 0.6 + f1 * 0.4 + f2 * 0.25) * env
    save_mp3(mono, "bruh_sound")
    print("✓ bruh_sound.mp3 ready")


def gen_metal_pipe():
    """Resonant metallic pipe crash with ringing harmonics."""
    dur = 2.2
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    modes = [(520, 1.0, 3.5), (835, 0.8, 4.0), (1240, 0.6, 5.0), (1890, 0.5, 6.0), (2850, 0.35, 8.0), (3900, 0.2, 10.0)]
    mono = np.zeros_like(t)
    for freq, amp, dec in modes:
        mono += amp * np.sin(2 * np.pi * freq * t) * np.exp(-dec * t)
    noise = np.random.normal(0, 0.4, len(t)) * np.exp(-35 * t)
    mono = (mono * 0.8 + noise * 0.5)
    left = mono
    right = np.pad(mono, (int(SR * 0.012), 0))[:len(mono)]
    save_mp3(np.column_stack([left, right]), "metal_pipe")
    print("✓ metal_pipe.mp3 ready")


def gen_airhorn_blast():
    """MLG 3-shot airhorn trumpet fanfare."""
    dur = 1.6
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    mono = np.zeros_like(t)
    # 3 stabs at 0.0s, 0.32s, 0.65s
    stabs = [0.0, 0.32, 0.65]
    for st in stabs:
        idx = int(st * SR)
        sub_t = t[:int(0.28 * SR)]
        # Airhorn rich brass tone around 466 Hz (Bb4) with pitch dive
        f_tone = 466 + 30 * np.exp(-15 * sub_t)
        p = 2 * np.pi * np.cumsum(f_tone) / SR
        stab = (np.sin(p) + 0.8 * np.sin(2 * p) + 0.6 * np.sin(3 * p) + 0.4 * np.sin(4 * p) + 0.3 * np.sin(5 * p))
        stab *= np.clip(sub_t / 0.02, 0, 1) * np.clip((0.28 - sub_t) / 0.04, 0, 1)
        end_idx = min(len(mono), idx + len(stab))
        mono[idx:end_idx] += stab[:end_idx - idx]
    save_mp3(mono, "airhorn_blast")
    print("✓ airhorn_blast.mp3 ready")


def gen_phonk_drift():
    """140 BPM Phonk Drift Beat with iconic 808 cowbells and trap drums."""
    bpm = 140
    beat_dur = 60.0 / bpm
    total_dur = 24.0  # ~24 seconds loop
    t = np.linspace(0, total_dur, int(SR * total_dur), endpoint=False)
    left = np.zeros_like(t)
    right = np.zeros_like(t)

    # 1. 808 Cowbell Melody (F# minor: F#4=370Hz, A4=440Hz, B4=494Hz, C#5=554Hz, E5=659Hz)
    cowbell_notes = [
        (0.0, 370), (0.5, 440), (1.0, 494), (1.5, 554),
        (2.0, 494), (2.5, 440), (3.0, 370), (3.5, 330),
        (4.0, 370), (4.5, 554), (5.0, 659), (5.5, 554),
        (6.0, 494), (6.5, 440), (7.0, 370), (7.5, 330)
    ]
    loop_beats = 8
    loop_time = loop_beats * beat_dur

    for loop_start in np.arange(0, total_dur, loop_time):
        for b_off, f_cb in cowbell_notes:
            t_hit = loop_start + b_off * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            cb_len = min(int(0.22 * SR), len(t) - idx)
            ct = np.linspace(0, cb_len / SR, cb_len, endpoint=False)
            # Two square/pulse sines creating resonant bell
            cb_wave = np.sin(2 * np.pi * f_cb * ct) + 0.6 * np.sin(2 * np.pi * (f_cb * 1.48) * ct)
            cb_env = np.exp(-12.0 * ct)
            cb_sound = np.clip(cb_wave * cb_env * 0.7, -0.9, 0.9)
            left[idx:idx + cb_len] += cb_sound
            right[idx:idx + cb_len] += cb_sound

    # 2. Trap Kick (beat 0, 2.5, 4.0, 6.5)
    kick_beats = [0.0, 2.5, 4.0, 6.5]
    for loop_start in np.arange(0, total_dur, loop_time):
        for kb in kick_beats:
            t_hit = loop_start + kb * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            k_len = min(int(0.35 * SR), len(t) - idx)
            kt = np.linspace(0, k_len / SR, k_len, endpoint=False)
            k_f = 45 + 120 * np.exp(-22 * kt)
            k_wave = np.tanh(2.2 * np.sin(2 * np.pi * np.cumsum(k_f) / SR)) * np.exp(-6 * kt)
            left[idx:idx + k_len] += k_wave * 0.9
            right[idx:idx + k_len] += k_wave * 0.9

    # 3. Snappy Snare/Clap on beats 2 and 6
    snare_beats = [2.0, 6.0]
    for loop_start in np.arange(0, total_dur, loop_time):
        for sb in snare_beats:
            t_hit = loop_start + sb * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            s_len = min(int(0.25 * SR), len(t) - idx)
            st = np.linspace(0, s_len / SR, s_len, endpoint=False)
            s_noise = np.random.normal(0, 0.4, s_len) * np.exp(-14 * st)
            s_tone = np.sin(2 * np.pi * 200 * st) * np.exp(-18 * st)
            s_sound = (s_noise + s_tone * 0.5) * 0.75
            left[idx:idx + s_len] += s_sound
            right[idx:idx + s_len] += s_sound

    # 4. Hi-hats every 8th note
    for ht_beat in np.arange(0, total_dur / beat_dur, 0.5):
        t_hit = ht_beat * beat_dur
        if t_hit >= total_dur:
            continue
        idx = int(t_hit * SR)
        h_len = min(int(0.06 * SR), len(t) - idx)
        ht = np.linspace(0, h_len / SR, h_len, endpoint=False)
        h_sound = np.random.normal(0, 0.15, h_len) * np.exp(-50 * ht)
        left[idx:idx + h_len] += h_sound * 0.8
        right[idx:idx + h_len] += h_sound * 0.6

    save_mp3(np.column_stack([left, right]), "phonk_drift")
    print("✓ phonk_drift.mp3 ready")


def gen_funny_sneaky():
    """120 BPM Quirky, Sneaky Pizzicato comedy tune with woodblock clicks."""
    bpm = 120
    beat_dur = 60.0 / bpm
    total_dur = 20.0
    t = np.linspace(0, total_dur, int(SR * total_dur), endpoint=False)
    left = np.zeros_like(t)
    right = np.zeros_like(t)

    # Pizzicato notes (C major scale tiptoe: C3=130Hz, E3=164Hz, G3=196Hz, B3=246Hz, C4=261Hz)
    pizz_phrase = [
        (0.0, 130), (0.5, 164), (1.0, 196), (1.5, 164),
        (2.0, 130), (2.5, 130), (3.0, 196), (3.5, 246),
        (4.0, 261), (4.5, 246), (5.0, 196), (5.5, 164),
        (6.0, 146), (6.5, 164), (7.0, 130), (7.5, 0)
    ]
    loop_beats = 8
    loop_time = loop_beats * beat_dur

    for loop_start in np.arange(0, total_dur, loop_time):
        for b_off, f in pizz_phrase:
            if f <= 0:
                continue
            t_hit = loop_start + b_off * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            p_len = min(int(0.18 * SR), len(t) - idx)
            pt = np.linspace(0, p_len / SR, p_len, endpoint=False)
            p_wave = (np.sin(2 * np.pi * f * pt) + 0.5 * np.sin(2 * np.pi * (2 * f) * pt)) * np.exp(-15 * pt)
            left[idx:idx + p_len] += p_wave * 0.8
            right[idx:idx + p_len] += p_wave * 0.8

    # Woodblock click on offbeats
    for b in np.arange(0.25, total_dur / beat_dur, 0.5):
        t_hit = b * beat_dur
        if t_hit >= total_dur:
            continue
        idx = int(t_hit * SR)
        wb_len = min(int(0.04 * SR), len(t) - idx)
        wbt = np.linspace(0, wb_len / SR, wb_len, endpoint=False)
        wb_sound = np.sin(2 * np.pi * 950 * wbt) * np.exp(-80 * wbt) * 0.3
        left[idx:idx + wb_len] += wb_sound
        right[idx:idx + wb_len] += wb_sound * 0.7

    save_mp3(np.column_stack([left, right]), "funny_sneaky")
    print("✓ funny_sneaky.mp3 ready")


def gen_dramatic_suspense():
    """60 BPM Dark cinematic suspense tension builder with pulsing heartbeat sub drone."""
    dur = 24.0
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)

    # 1. Dark sub drone (45 Hz) with slow filter swell
    drone = np.sin(2 * np.pi * 45 * t) + 0.3 * np.sin(2 * np.pi * 90 * t)
    pulse = 0.5 + 0.5 * np.sin(2 * np.pi * (60.0 / 60.0) * t)  # 1 pulse per sec
    drone = drone * (0.6 + 0.4 * pulse)

    # 2. Heartbeat double thumps
    heartbeat = np.zeros_like(t)
    for beat in np.arange(0, dur, 1.0):
        for sub_off in [0.0, 0.22]:
            idx = int((beat + sub_off) * SR)
            if idx < len(t):
                h_len = min(int(0.18 * SR), len(t) - idx)
                ht = np.linspace(0, h_len / SR, h_len, endpoint=False)
                hb = np.sin(2 * np.pi * 50 * ht) * np.exp(-16 * ht)
                heartbeat[idx:idx + h_len] += hb * 0.75

    # 3. Eerie high tension dissonance (F#5 + G5 minor second)
    strings = (np.sin(2 * np.pi * 740 * t) + np.sin(2 * np.pi * 784 * t)) * 0.15
    rising_amp = np.clip(t / dur, 0.2, 1.0)
    strings *= rising_amp

    mono = drone * 0.7 + heartbeat * 0.6 + strings * 0.4
    left = mono
    right = np.pad(mono, (int(SR * 0.015), 0))[:len(mono)]
    save_mp3(np.column_stack([left, right]), "dramatic_suspense")
    print("✓ dramatic_suspense.mp3 ready")


def gen_hype_trap():
    """145 BPM High-energy trap victory anthem with brass stabs and rolling 808s."""
    bpm = 145
    beat_dur = 60.0 / bpm
    total_dur = 20.0
    t = np.linspace(0, total_dur, int(SR * total_dur), endpoint=False)
    left = np.zeros_like(t)
    right = np.zeros_like(t)

    # Brass stabs (D minor triad: D4=293Hz, F4=349Hz, A4=440Hz, D5=587Hz)
    stab_beats = [0.0, 0.75, 1.5, 3.0, 4.0, 4.75, 5.5, 7.0]
    loop_beats = 8
    loop_time = loop_beats * beat_dur

    for loop_start in np.arange(0, total_dur, loop_time):
        for sb in stab_beats:
            t_hit = loop_start + sb * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            b_len = min(int(0.28 * SR), len(t) - idx)
            bt = np.linspace(0, b_len / SR, b_len, endpoint=False)
            brass = (np.sin(2 * np.pi * 293 * bt) + 0.8 * np.sin(2 * np.pi * 349 * bt) +
                     0.7 * np.sin(2 * np.pi * 440 * bt) + 0.5 * np.sin(2 * np.pi * 587 * bt))
            b_env = np.clip(bt / 0.01, 0, 1) * np.exp(-7.0 * bt)
            b_sound = np.tanh(2.0 * brass * b_env) * 0.65
            left[idx:idx + b_len] += b_sound
            right[idx:idx + b_len] += b_sound

    # 808 Sub Kick on beats 0, 1.5, 3.0, 4.0, 5.5, 7.0
    for loop_start in np.arange(0, total_dur, loop_time):
        for kb in [0.0, 1.5, 3.0, 4.0, 5.5]:
            t_hit = loop_start + kb * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            k_len = min(int(0.38 * SR), len(t) - idx)
            kt = np.linspace(0, k_len / SR, k_len, endpoint=False)
            kf = 50 + 110 * np.exp(-18 * kt)
            kw = np.sin(2 * np.pi * np.cumsum(kf) / SR) * np.exp(-5.0 * kt)
            left[idx:idx + k_len] += kw * 0.85
            right[idx:idx + k_len] += kw * 0.85

    # Snare on 2 and 6
    for loop_start in np.arange(0, total_dur, loop_time):
        for sb in [2.0, 6.0]:
            t_hit = loop_start + sb * beat_dur
            if t_hit >= total_dur:
                continue
            idx = int(t_hit * SR)
            s_len = min(int(0.2 * SR), len(t) - idx)
            st = np.linspace(0, s_len / SR, s_len, endpoint=False)
            sn = np.random.normal(0, 0.45, s_len) * np.exp(-15 * st)
            left[idx:idx + s_len] += sn * 0.7
            right[idx:idx + s_len] += sn * 0.7

    save_mp3(np.column_stack([left, right]), "hype_trap")
    print("✓ hype_trap.mp3 ready")


def gen_chill_lofi():
    """82 BPM Relaxed Lo-Fi Hip Hop with warm Rhodes chords and vinyl crackle."""
    bpm = 82
    beat_dur = 60.0 / bpm
    total_dur = 24.0
    t = np.linspace(0, total_dur, int(SR * total_dur), endpoint=False)

    # Vinyl crackle noise
    crackle = np.random.normal(0, 0.04, len(t))
    crackle[np.random.rand(len(t)) > 0.003] = 0.0
    crackle = np.convolve(crackle, np.ones(8) / 8, mode="same")

    # Rhodes chords (Dm9: D3, F3, A3, C4, E4 -> G13: G2, F3, B3, E4 -> Cmaj9: C3, E3, G3, B3, D4)
    chords = [
        (0.0, [146, 174, 220, 261, 330]),
        (4.0, [98, 174, 246, 330]),
        (8.0, [130, 164, 196, 246, 293]),
        (12.0, [110, 164, 220, 261, 330])
    ]
    rhodes = np.zeros_like(t)
    for c_beat, notes in chords:
        t_hit = c_beat * beat_dur
        if t_hit >= total_dur:
            continue
        idx = int(t_hit * SR)
        c_len = min(int(3.5 * SR), len(t) - idx)
        ct = np.linspace(0, c_len / SR, c_len, endpoint=False)
        chord_w = np.zeros(c_len)
        for note in notes:
            chord_w += (np.sin(2 * np.pi * note * ct) + 0.3 * np.sin(2 * np.pi * (2 * note) * ct))
        env = np.clip(ct / 0.05, 0, 1) * np.exp(-0.8 * ct)
        rhodes[idx:idx + c_len] += chord_w * env * 0.18

    # Soft Lo-Fi Kick & Rimshot
    drums = np.zeros_like(t)
    for b in np.arange(0, total_dur / beat_dur, 4.0):
        # Kick on 0, 2.5
        for kb in [0.0, 2.5]:
            idx = int((b + kb) * beat_dur * SR)
            if idx < len(t):
                klen = min(int(0.25 * SR), len(t) - idx)
                kt = np.linspace(0, klen / SR, klen, endpoint=False)
                drums[idx:idx + klen] += np.sin(2 * np.pi * (65 * np.exp(-10 * kt)) * kt) * np.exp(-6 * kt) * 0.5
        # Snare/Rim on 2.0
        idx = int((b + 2.0) * beat_dur * SR)
        if idx < len(t):
            slen = min(int(0.12 * SR), len(t) - idx)
            st = np.linspace(0, slen / SR, slen, endpoint=False)
            drums[idx:idx + slen] += (np.random.normal(0, 0.2, slen) + np.sin(2 * np.pi * 320 * st) * 0.3) * np.exp(-25 * st) * 0.4

    mono = (rhodes * 0.75 + drums * 0.65 + crackle * 0.2)
    left = mono
    right = np.pad(mono, (int(SR * 0.018), 0))[:len(mono)]
    save_mp3(np.column_stack([left, right]), "chill_lofi")
    print("✓ chill_lofi.mp3 ready")


def gen_sad_violin():
    """Melancholic minor violin/cello sorrowful progression for fail and L moments."""
    dur = 18.0
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    # D minor descending progression: Dm -> Bb -> F -> A
    notes_time = [
        (0.0, 293), (4.0, 233), (8.0, 174), (12.0, 220)
    ]
    strings = np.zeros_like(t)
    for st_sec, f in notes_time:
        idx = int(st_sec * SR)
        s_len = min(int(4.2 * SR), len(t) - idx)
        st = np.linspace(0, s_len / SR, s_len, endpoint=False)
        # Vibrato 5.5 Hz
        vib = 1.0 + 0.015 * np.sin(2 * np.pi * 5.5 * st)
        w = (np.sin(2 * np.pi * f * vib * st) + 0.5 * np.sin(2 * np.pi * (2 * f) * vib * st) +
             0.25 * np.sin(2 * np.pi * (3 * f) * vib * st))
        env = np.clip(st / 0.4, 0, 1) * np.clip((4.2 - st) / 0.8, 0, 1)
        strings[idx:idx + s_len] += w * env * 0.6

    left = strings
    right = np.pad(strings, (int(SR * 0.02), 0))[:len(strings)]
    save_mp3(np.column_stack([left, right]), "sad_violin_l")
    print("✓ sad_violin_l.mp3 ready")


def main():
    print("Synthesizing 10 pristine background music tracks and meme sounds...")
    gen_vine_boom()
    gen_bruh_sound()
    gen_metal_pipe()
    gen_airhorn_blast()
    gen_phonk_drift()
    gen_funny_sneaky()
    gen_dramatic_suspense()
    gen_hype_trap()
    gen_chill_lofi()
    gen_sad_violin()
    print("All 10 tracks synthesized successfully in web/audio/!")


if __name__ == "__main__":
    main()
