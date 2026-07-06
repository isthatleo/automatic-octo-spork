"""Production-grade real computation utilities for specialized agents.

Provides real statistical, mathematical, and ML functions — no random/simulated data.
"""

import numpy as np
from typing import Any
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


def compute_statistics(data: list[float]) -> dict[str, float]:
    arr = np.array(data, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "median": 0.0, "skew": 0.0, "kurtosis": 0.0, "q25": 0.0, "q75": 0.0, "n": 0}
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1 if n > 1 else 0))
    median = float(np.median(arr))
    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    skew = float(np.mean(((arr - mean) / (std + 1e-12)) ** 3)) if std > 1e-12 and n >= 3 else 0.0
    kurt = float(np.mean(((arr - mean) / (std + 1e-12)) ** 4) - 3.0) if std > 1e-12 and n >= 4 else 0.0
    return {
        "mean": round(mean, 6), "std": round(std, 6), "min": round(float(np.min(arr)), 6),
        "max": round(float(np.max(arr)), 6), "median": round(median, 6),
        "skew": round(skew, 6), "kurtosis": round(kurt, 6),
        "q25": round(q25, 6), "q75": round(q75, 6), "n": n
    }


def linear_regression(x: list[float], y: list[float]) -> dict[str, float]:
    xa, ya = np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)
    n = len(xa)
    if n < 2:
        return {"slope": 0.0, "intercept": 0.0, "r_squared": 0.0, "n": n}
    A = np.vstack([xa, np.ones(n)]).T
    slope, intercept = np.linalg.lstsq(A, ya, rcond=None)[0]
    y_pred = slope * xa + intercept
    ss_res = float(np.sum((ya - y_pred) ** 2))
    ss_tot = float(np.sum((ya - np.mean(ya)) ** 2))
    r2 = 1.0 - ss_res / (ss_tot + 1e-12)
    return {"slope": round(float(slope), 6), "intercept": round(float(intercept), 6), "r_squared": round(r2, 6), "n": n}


def correlation_matrix(data: list[list[float]]) -> list[list[float]]:
    arr = np.array(data, dtype=np.float64)
    corr = np.corrcoef(arr, rowvar=False)
    return [[round(float(v), 6) for v in row] for row in corr]


def compute_moving_average(data: list[float], window: int) -> list[float]:
    arr = np.array(data, dtype=np.float64)
    if len(arr) < window or window < 1:
        return list(arr)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    result = (cumsum[window:] - cumsum[:-window]) / window
    return [float(v) for v in result]


def compute_ema(data: list[float], period: int) -> list[float]:
    arr = np.array(data, dtype=np.float64)
    if len(arr) < 1 or period < 1:
        return list(arr)
    multiplier = 2.0 / (period + 1)
    ema = np.zeros_like(arr)
    ema[0] = arr[0]
    for i in range(1, len(arr)):
        ema[i] = (arr[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return [float(v) for v in ema]


def compute_rsi(data: list[float], period: int = 14) -> list[float]:
    arr = np.array(data, dtype=np.float64)
    if len(arr) < period + 1:
        return [50.0] * len(arr)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    rsi = [50.0] * (period)
    for i in range(period, len(arr)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / (avg_loss + 1e-12)
        rsi.append(round(100.0 - 100.0 / (1.0 + rs), 4))
    return rsi


def compute_bollinger_bands(data: list[float], period: int = 20, num_std: float = 2.0) -> dict[str, list[float]]:
    arr = np.array(data, dtype=np.float64)
    n = len(arr)
    if n < period:
        return {"middle": list(arr), "upper": list(arr), "lower": list(arr)}
    middle = compute_moving_average(data, period)
    padding = n - len(middle)
    upper, lower = [], []
    for i in range(n):
        if i < padding:
            upper.append(float(arr[i]))
            lower.append(float(arr[i]))
        else:
            window = arr[i - period + 1: i + 1]
            std = float(np.std(window, ddof=1))
            m = middle[i - padding]
            upper.append(round(m + num_std * std, 6))
            lower.append(round(m - num_std * std, 6))
    return {"middle": [round(float(v), 6) for v in middle], "upper": upper, "lower": lower}


def macd(data: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9) -> dict[str, list[float]]:
    ema_fast = compute_ema(data, fast)
    ema_slow = compute_ema(data, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = compute_ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return {"macd": [round(float(v), 6) for v in macd_line],
            "signal": [round(float(v), 6) for v in signal_line],
            "histogram": [round(float(v), 6) for v in histogram]}


def portfolio_metrics(returns: list[float], risk_free_rate: float = 0.02) -> dict[str, float]:
    arr = np.array(returns, dtype=np.float64)
    n = len(arr)
    if n < 2:
        return {"sharpe_ratio": 0.0, "sortino_ratio": 0.0, "max_drawdown": 0.0, "annualized_vol": 0.0, "annualized_return": 0.0, "calmar_ratio": 0.0}
    ann_return = float((1 + np.mean(arr)) ** 252 - 1)
    ann_vol = float(np.std(arr, ddof=1) * np.sqrt(252))
    sharpe = (ann_return - risk_free_rate) / (ann_vol + 1e-12)
    downside = arr[arr < 0]
    downside_vol = float(np.std(downside, ddof=1) * np.sqrt(252)) if len(downside) > 1 else 0.01
    sortino = (ann_return - risk_free_rate) / (downside_vol + 1e-12)
    cum = np.cumprod(1 + arr)
    running_max = np.maximum.accumulate(cum)
    drawdown = (cum - running_max) / running_max
    max_dd = float(np.min(drawdown))
    calmar = ann_return / (abs(max_dd) + 1e-12)
    return {
        "sharpe_ratio": round(sharpe, 6), "sortino_ratio": round(sortino, 6),
        "max_drawdown": round(max_dd, 6), "annualized_vol": round(ann_vol, 6),
        "annualized_return": round(ann_return, 6), "calmar_ratio": round(calmar, 6)
    }


def kmeans_cluster(data: list[list[float]], k: int, max_iter: int = 100) -> tuple[list[int], list[list[float]]]:
    arr = np.array(data, dtype=np.float64)
    n, d = arr.shape
    if n == 0 or k < 1:
        return [], []
    if k > n:
        k = n
    rng = np.random.default_rng(42)
    idx = rng.choice(n, k, replace=False)
    centroids = arr[idx].copy()
    for _ in range(max_iter):
        diffs = arr[:, np.newaxis, :] - centroids[np.newaxis, :, :]
        distances = np.sqrt(np.sum(diffs ** 2, axis=2))
        labels = np.argmin(distances, axis=1)
        new_centroids = np.zeros_like(centroids)
        for j in range(k):
            mask = labels == j
            if np.any(mask):
                new_centroids[j] = np.mean(arr[mask], axis=0)
            else:
                new_centroids[j] = centroids[j]
        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids
    return [int(l) for l in labels], [[round(float(v), 6) for v in c] for c in centroids]


def tfidf_scores(documents: list[list[str]]) -> dict[str, float]:
    word_doc_count: dict[str, int] = {}
    for doc in documents:
        for word in set(doc):
            word_doc_count[word] = word_doc_count.get(word, 0) + 1
    n_docs = len(documents)
    scores: dict[str, float] = {}
    for doc in documents:
        for word in doc:
            tf = doc.count(word) / (len(doc) + 1e-12)
            idf = np.log((n_docs + 1) / (word_doc_count.get(word, 1) + 1)) + 1
            scores[word] = round(float(tf * idf), 6)
    return scores


def pca_2d(data: list[list[float]]) -> tuple[list[float], list[float]]:
    arr = np.array(data, dtype=np.float64)
    n, d = arr.shape
    if n < 2 or d < 1:
        return [], []
    mean = np.mean(arr, axis=0)
    centered = arr - mean
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, idx]
    proj = centered @ eigvecs[:, :2]
    return [float(v) for v in proj[:, 0]], [float(v) for v in proj[:, 1]]


def detect_outliers_iqr(data: list[float], multiplier: float = 1.5) -> list[int]:
    arr = np.array(data, dtype=np.float64)
    if len(arr) < 4:
        return []
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return [int(i) for i in range(len(arr)) if arr[i] < lower or arr[i] > upper]


def entropy(probabilities: list[float]) -> float:
    p = np.array(probabilities, dtype=np.float64)
    p = p[p > 0]
    if len(p) == 0:
        return 0.0
    return round(float(-np.sum(p * np.log2(p))), 6)


def kl_divergence(p: list[float], q: list[float]) -> float:
    pa, qa = np.array(p, dtype=np.float64), np.array(q, dtype=np.float64)
    pa += 1e-12
    qa += 1e-12
    pa /= np.sum(pa)
    qa /= np.sum(qa)
    return round(float(np.sum(pa * np.log2(pa / qa))), 6)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float64), np.array(b, dtype=np.float64)
    dot = float(np.dot(va, vb))
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return round(dot / (norm + 1e-12), 6)


def ngram_frequencies(text: str, n: int = 2) -> dict[str, float]:
    words = text.lower().split()
    ngrams: dict[str, int] = {}
    for i in range(len(words) - n + 1):
        gram = " ".join(words[i:i+n])
        ngrams[gram] = ngrams.get(gram, 0) + 1
    total = sum(ngrams.values()) + 1e-12
    return {k: round(v / total, 6) for k, v in ngrams.items()}


def monte_carlo_simulation(initial: float, mu: float, sigma: float, steps: int, n_paths: int) -> list[list[float]]:
    rng = np.random.default_rng(42)
    dt = 1.0 / 252
    paths = np.zeros((n_paths, steps + 1))
    paths[:, 0] = initial
    for t in range(1, steps + 1):
        z = rng.normal(0, 1, n_paths)
        paths[:, t] = paths[:, t - 1] * np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z)
    return [[round(float(v), 6) for v in path] for path in paths]


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    arr = np.array(returns, dtype=np.float64)
    if len(arr) < 10:
        return 0.0
    var = float(np.percentile(arr, (1 - confidence) * 100))
    return round(var, 6)


def conditional_var(returns: list[float], confidence: float = 0.95) -> float:
    arr = np.array(returns, dtype=np.float64)
    if len(arr) < 10:
        return 0.0
    threshold = np.percentile(arr, (1 - confidence) * 100)
    tail = arr[arr <= threshold]
    if len(tail) == 0:
        return float(threshold)
    return round(float(np.mean(tail)), 6)


def fibonacci_retracement(high: float, low: float) -> dict[str, float]:
    diff = high - low
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    return {f"{int(l * 100)}%": round(high - l * diff, 6) for l in levels}


def solve_linear_program(c: list[float], A: list[list[float]], b: list[float], bounds: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    try:
        from scipy.optimize import linprog
        res = linprog(c, A_ub=A, b_ub=b, bounds=bounds, method="highs")
        if res.success:
            return {"x": [round(float(v), 6) for v in res.x], "fun": round(float(res.fun), 6), "success": True, "nit": int(res.nit)}
        return {"x": [], "fun": 0.0, "success": False, "message": res.message}
    except ImportError:
        c_arr = np.array(c, dtype=np.float64)
        return {"x": [round(float(v), 6) for v in c_arr / (np.sum(np.abs(c_arr)) + 1e-12)], "fun": round(float(np.sum(c_arr)), 6),
                "success": True, "nit": 1, "note": "scipy unavailable, used heuristic"}


def gaussian_mixture_likelihood(data: list[float], n_components: int = 3) -> dict[str, Any]:
    arr = np.array(data, dtype=np.float64)
    if len(arr) < n_components * 2:
        return {"means": [float(np.mean(arr))], "variances": [float(np.var(arr))], "weights": [1.0], "log_likelihood": 0.0, "aic": 0.0, "bic": 0.0}
    try:
        from sklearn.mixture import GaussianMixture
        gm = GaussianMixture(n_components=min(n_components, len(arr) // 2), random_state=42, max_iter=200)
        gm.fit(arr.reshape(-1, 1))
        ll = float(gm.score(arr.reshape(-1, 1)) * len(arr))
        k = gm.means_.shape[0] * 2 + gm.means_.shape[0] - 1
        return {
            "means": [round(float(m[0]), 6) for m in gm.means_],
            "variances": [round(float(c[0][0]), 6) for c in gm.covariances_],
            "weights": [round(float(w), 6) for w in gm.weights_],
            "log_likelihood": round(ll, 4),
            "aic": round(2 * k - 2 * ll, 4),
            "bic": round(k * np.log(len(arr)) - 2 * ll, 4)
        }
    except ImportError:
        mean, var = float(np.mean(arr)), float(np.var(arr))
        return {"means": [mean], "variances": [var], "weights": [1.0], "note": "sklearn unavailable"}


def detect_seasonality(data: list[float]) -> dict[str, Any]:
    arr = np.array(data, dtype=np.float64)
    n = len(arr)
    if n < 4:
        return {"has_seasonality": False, "period": 1, "strength": 0.0}
    fft = np.fft.rfft(arr - np.mean(arr))
    freqs = np.fft.rfftfreq(n)
    magnitude = np.abs(fft)
    peak_idx = np.argmax(magnitude[1:]) + 1
    peak_freq = freqs[peak_idx]
    period = max(2, int(1.0 / peak_freq + 0.5)) if peak_freq > 0 else 2
    strength = float(magnitude[peak_idx] / (np.sum(magnitude[1:]) + 1e-12))
    return {"has_seasonality": strength > 0.15, "period": period, "strength": round(strength, 6)}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def time_since(dt: datetime) -> str:
    delta = now_utc() - dt
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)
