import numpy as np


def psi(reference, current, bins=10):
    """Compare feature distributions using bins from the reference sample."""
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    if not len(reference) or not len(current):
        raise ValueError('Both samples must be non-empty')
    boundaries = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(boundaries) < 2:
        raise ValueError('Reference sample must vary')
    boundaries[0], boundaries[-1] = -np.inf, np.inf
    ref = np.histogram(reference, bins=boundaries)[0] / len(reference)
    cur = np.histogram(current, bins=boundaries)[0] / len(current)
    ref = np.clip(ref, 1e-6, None)
    cur = np.clip(cur, 1e-6, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))
