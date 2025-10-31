from math import exp, sqrt
from typing import Dict, Tuple

# Emotion anchors for Valence (V) and Arousal (A)
EMOTION_VA: Dict[str, Tuple[float, float]] = {
    "happy":    (+0.80, +0.60),
    "sad":      (-0.70, -0.40),
    "neutral":  ( 0.00,  0.00),
    "angry":    (-0.70, +0.80),
    "fear":     (-0.60, +0.70),
    "surprise": ( 0.00, +0.85),
}


def magnitude_to_arousal(magnitude: float, k: float = 3.0) -> float:
    """Map text magnitude to arousal in [0,1] using A_text = 1 - exp(-magnitude/k)."""
    if magnitude <= 0:
        return 0.0
    try:
        return max(0.0, min(1.0, 1.0 - exp(-magnitude / k)))
    except Exception:
        return 0.0


def audio_probs_to_VA(audio_probs: Dict[str, float]) -> Tuple[float, float]:
    """Compute (V_audio, A_audio) as weighted sum of anchors by audio_probs."""
    v = 0.0
    a = 0.0
    for emo, p in audio_probs.items():
        anchor = EMOTION_VA.get(emo)
        if not anchor:
            continue
        try:
            p_val = float(p)
        except Exception:
            p_val = 0.0
        v += p_val * anchor[0]
        a += p_val * anchor[1]
    return v, a


def adaptive_weights_for_valence(audio_probs: Dict[str, float], score: float, a_text: float) -> float:
    """Compute alpha (text vs audio weight) for Valence.
    alpha = conf_audio_V / (conf_audio_V + conf_text_V + 1e-8)
    where conf_text_V = |score|*A_text, conf_audio_V = max(p_e)
    """
    conf_text_v = abs(score) * max(0.0, min(1.0, a_text))
    conf_audio_v = max([0.0] + [float(p) for p in audio_probs.values()])
    denom = conf_audio_v + conf_text_v + 1e-8
    return 0.0 if denom == 0 else max(0.0, min(1.0, conf_audio_v / denom))


def adaptive_weights_for_arousal(audio_probs: Dict[str, float], a_audio: float, a_text: float) -> float:
    """Compute beta for Arousal.
    beta = conf_audio_A / (conf_audio_A + conf_text_A + 1e-8)
    where conf_text_A = A_text, conf_audio_A = |A_audio|
    """
    conf_text_a = max(0.0, min(1.0, a_text))
    conf_audio_a = abs(a_audio)
    denom = conf_audio_a + conf_text_a + 1e-8
    return 0.0 if denom == 0 else max(0.0, min(1.0, conf_audio_a / denom))


def _cosine_similarity(x: Tuple[float, float], y: Tuple[float, float]) -> float:
    """Cosine similarity between two 2D vectors, clipped to [0,1] (negatives -> 0)."""
    vx, vy = x
    ax, ay = y
    num = vx * ax + vy * ay
    den = (sqrt(vx * vx + vy * vy) * sqrt(ax * ax + ay * ay)) or 1e-8
    sim = num / den
    return max(0.0, sim)


def _normalize_to_bps(scores: Dict[str, float]) -> Dict[str, int]:
    """Normalize non-negative scores to sum=10000 (bps), with rounding diff fix."""
    total = sum(max(0.0, s) for s in scores.values())
    if total <= 0:
        # fallback: neutral only
        base = {k: 0 for k in scores.keys()}
        if "neutral" in base:
            base["neutral"] = 10000
        else:
            # assign all to max key if exists
            if scores:
                first_key = next(iter(scores))
                base[first_key] = 10000
        return base
    scaled = {k: int(round(max(0.0, s) * (10000.0 / total))) for k, s in scores.items()}
    diff = 10000 - sum(scaled.values())
    if diff != 0 and scaled:
        key_max = max(scaled, key=lambda k: scaled[k])
        scaled[key_max] = max(0, min(10000, scaled[key_max] + diff))
    return scaled


def to_bps_from_unit_minus1_1(x: float) -> int:
    """Map [-1,1] -> [0,10000] linearly."""
    try:
        xv = max(-1.0, min(1.0, float(x)))
        return int(round((xv + 1.0) * 5000.0))
    except Exception:
        return 0


def to_x1000(x: float) -> int:
    """Scale float to int×1000 with rounding."""
    try:
        return int(round(float(x) * 1000.0))
    except Exception:
        return 0


def fuse_VA(audio_probs: Dict[str, float], text_score: float, text_magnitude: float) -> Dict[str, object]:
    """Fuse audio (emotion probabilities) and text (score,magnitude) into composite VA.

    Returns dict with keys:
      - V_final, A_final, intensity, V_audio, A_audio, V_text, A_text, alpha, beta (float)
      - per_emotion_bps (dict[str,int], sum=10000), top_emotion (str), top_confidence_bps (int)
    """
    # Audio -> VA
    v_audio, a_audio = audio_probs_to_VA(audio_probs)

    # Text -> VA
    v_text = max(-1.0, min(1.0, float(text_score)))
    a_text = magnitude_to_arousal(float(text_magnitude))

    # Adaptive weights
    alpha = adaptive_weights_for_valence(audio_probs, v_text, a_text)
    beta = adaptive_weights_for_arousal(audio_probs, a_audio, a_text)

    # Final fusion
    v_final = alpha * v_audio + (1.0 - alpha) * v_text
    a_final = beta * a_audio + (1.0 - beta) * a_text
    intensity = sqrt(v_final * v_final + a_final * a_final)

    # Cosine similarities to anchors (negative clipped to 0), normalize to bps
    sims: Dict[str, float] = {}
    for emo, (v_e, a_e) in EMOTION_VA.items():
        sims[emo] = _cosine_similarity((v_final, a_final), (v_e, a_e))
    # surprise down-weighting before normalization
    sims["surprise"] = sims.get("surprise", 0.0) * 0.3
    per_emotion_bps = _normalize_to_bps(sims)

    # optional cap after normalization (e.g., surprise <= 10%)
    cap = 1000  # adjust if needed
    sur = per_emotion_bps.get("surprise", 0)
    if sur > cap:
        over = sur - cap
        per_emotion_bps["surprise"] = cap
        others = {k: v for k, v in per_emotion_bps.items() if k != "surprise" and v > 0}
        total_others = sum(others.values()) or 1
        for k in others:
            inc = round(over * (per_emotion_bps[k] / total_others))
            per_emotion_bps[k] += int(inc)
        # rounding diff fix
        diff = 10000 - sum(per_emotion_bps.values())
        if diff != 0 and per_emotion_bps:
            kmax = max(per_emotion_bps, key=lambda k: per_emotion_bps[k])
            per_emotion_bps[kmax] += diff

    # Top emotion/confidence
    if per_emotion_bps:
        top_emotion = max(per_emotion_bps, key=lambda k: per_emotion_bps[k])
        top_confidence_bps = per_emotion_bps[top_emotion]
    else:
        top_emotion = "neutral"
        top_confidence_bps = 10000

    return {
        "V_final": v_final,
        "A_final": a_final,
        "intensity": intensity,
        "V_audio": v_audio,
        "A_audio": a_audio,
        "V_text": v_text,
        "A_text": a_text,
        "alpha": alpha,
        "beta": beta,
        "per_emotion_bps": per_emotion_bps,
        "top_emotion": top_emotion,
        "top_confidence_bps": top_confidence_bps,
    }
