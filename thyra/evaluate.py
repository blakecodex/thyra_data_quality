"""the backtest the gate reads: two models, one held-out window, more than one number.

the champion is the model in production. the challenger is the one asking to replace
it. the question is not "is the challenger accurate" but "is it better than what we
have, and is it better everywhere the money is". so the errors are paired row by row,
the difference is bootstrapped so noise cannot promote a model, and the same table is
cut by hub and by hour block. the band the challenger promises is checked for coverage,
and the features it will see are compared with the ones it was trained on.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from .features import NUMERIC

BLOCKS = ("off_peak", "shoulder", "peak")


@dataclass
class Segment:
    name: str
    n: int
    mae_champion: float
    mae_challenger: float
    diff: float          # challenger minus champion; negative means the challenger is better
    lo: float            # 2.5th percentile of the bootstrapped mean difference
    hi: float            # 97.5th percentile


@dataclass
class Report:
    n_test: int
    overall: Segment
    by_block: list[Segment] = field(default_factory=list)
    by_hub: list[Segment] = field(default_factory=list)
    pinball_champion: float = 0.0
    pinball_challenger: float = 0.0
    coverage_challenger: float = 0.0
    psi: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def paired_bootstrap(diff: np.ndarray, draws: int = 2000, seed: int = 7) -> tuple[float, float]:
    """the 2.5th and 97.5th percentiles of the mean of resampled per-row differences.

    rows are resampled, not models, so the two error series stay paired: the same hour,
    the same hub, two forecasts. that is what makes the band about the difference and
    not about the level of either model.
    """
    rng = np.random.default_rng(seed)
    n = len(diff)
    if n == 0:
        return float("nan"), float("nan")
    idx = rng.integers(0, n, size=(draws, n))
    means = diff[idx].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def pinball(y: np.ndarray, lo: np.ndarray, hi: np.ndarray, q_lo: float = 0.05, q_hi: float = 0.95) -> float:
    """mean pinball loss of the two band edges; lower is sharper, given coverage."""
    def one(q, pred):
        d = y - pred
        return np.mean(np.maximum(q * d, (q - 1) * d))
    return float((one(q_lo, lo) + one(q_hi, hi)) / 2)


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10, floor: float = 1e-4) -> float:
    """population stability index with three guards: reference-quantile edges, merged duplicate edges, floored shares.

    with no change at all the index is not zero; it sits near (bins - 1) * (1/n + 1/m). read it against that, not against zero.
    """
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.maximum(np.histogram(reference, bins=edges)[0] / len(reference), floor)
    c = np.maximum(np.histogram(current, bins=edges)[0] / len(current), floor)
    return float(np.sum((c - r) * np.log(c / r)))


def _segment(name: str, y: np.ndarray, p_ch: np.ndarray, p_cl: np.ndarray, seed: int) -> Segment:
    e_ch, e_cl = np.abs(y - p_ch), np.abs(y - p_cl)
    diff = e_cl - e_ch
    lo, hi = paired_bootstrap(diff, seed=seed)
    return Segment(name=name, n=int(len(y)), mae_champion=float(e_ch.mean()), mae_challenger=float(e_cl.mean()), diff=float(diff.mean()), lo=lo, hi=hi)


def backtest(champion, challenger, reference: pd.DataFrame, test: pd.DataFrame, seed: int = 7) -> Report:
    """score both models on the held-out window. reference is the recent training window the features are compared against."""
    y = test["y"].to_numpy(float)
    p_ch, p_cl = champion.predict(test), challenger.predict(test)
    overall = _segment("overall", y, p_ch, p_cl, seed)
    by_block = []
    for b in BLOCKS:
        m = (test["block"] == b).to_numpy()
        by_block.append(_segment(b, y[m], p_ch[m], p_cl[m], seed))
    by_hub = []
    for h in sorted(test["hub"].unique()):
        m = (test["hub"] == h).to_numpy()
        by_hub.append(_segment(h, y[m], p_ch[m], p_cl[m], seed))
    lo_ch, hi_ch = champion.band(test)
    lo_cl, hi_cl = challenger.band(test)
    coverage = float(np.mean((y >= lo_cl) & (y <= hi_cl)))
    drift = {c: psi(reference[c].to_numpy(float), test[c].to_numpy(float)) for c in NUMERIC}
    return Report(
        n_test=int(len(test)),
        overall=overall,
        by_block=by_block,
        by_hub=by_hub,
        pinball_champion=pinball(y, lo_ch, hi_ch),
        pinball_challenger=pinball(y, lo_cl, hi_cl),
        coverage_challenger=coverage,
        psi=drift,
    )


def render(report: Report, gated: list[str] | None = None) -> str:
    """the backtest as a person reads it. gated names the features the drift check reads; the rest are printed for the reader."""
    def row(s: Segment) -> str:
        return f"  {s.name:10s} n {s.n:6d}  mae {s.mae_champion:6.3f} -> {s.mae_challenger:6.3f}  diff {s.diff:+.3f} [{s.lo:+.3f}, {s.hi:+.3f}]"
    lines = [f"backtest on {report.n_test} held-out hub-hours (challenger minus champion; negative is better)", row(report.overall), "by hour block"]
    lines += [row(s) for s in report.by_block]
    lines.append("by hub")
    lines += [row(s) for s in report.by_hub]
    lines.append(f"  pinball    {report.pinball_champion:.3f} -> {report.pinball_challenger:.3f}   90% band coverage (challenger) {report.coverage_challenger:.3f}")
    gated = list(report.psi) if gated is None else [g for g in gated if g in report.psi]
    parts = [f"{k} {v:.3f}" + ("" if k in gated else " (season, not gated)") for k, v in report.psi.items()]
    lines.append("  psi        " + ", ".join(parts))
    return "\n".join(lines)
