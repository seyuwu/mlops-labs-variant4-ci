"""Синтетические данные: фиксированное зерно и контролируемый сдвиг."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def generate(rows, seed, shift=False):
    rng = np.random.default_rng(seed)
    attendance = rng.beta(2.5, 2, rows)
    completed = rng.beta(2.2, 2, rows)
    hours = np.clip(rng.gamma(2.5, 2, rows), 0, 24)
    inactive = np.clip(rng.exponential(5, rows), 0, 45)
    prior = np.clip(rng.normal(65, 16, rows), 0, 100)
    if shift:
        attendance = np.clip(attendance * 0.6, 0, 1)
        inactive = np.clip(inactive + 9, 0, 60)
    signal = (0.028 * inactive + 0.8 * (1 - attendance) + 0.7 * (1 - completed)
              - 0.045 * hours - 0.004 * (prior - 50) - 0.65)
    if shift:
        # A deliberate concept shift makes the established rule unreliable.
        signal = -signal
    dropout = (signal + rng.normal(0, 0.10, rows) > 0).astype(int)
    return pd.DataFrame({'attendance': attendance, 'completed_percent': completed * 100,
                         'weekly_hours': hours, 'days_inactive': inactive,
                         'prior_score': prior, 'dropout': dropout}).round(4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='data/raw.csv')
    parser.add_argument('--rows', type=int, default=2400)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--shift', action='store_true')
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = generate(args.rows, args.seed, args.shift)
    frame.to_csv(output, index=False)
    print(f'{output}: rows={len(frame)}, dropout_rate={frame.dropout.mean():.3f}, shift={args.shift}')


if __name__ == '__main__':
    main()
