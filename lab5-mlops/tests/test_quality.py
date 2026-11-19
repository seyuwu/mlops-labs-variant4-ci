import json
import os
from pathlib import Path
import joblib
import pandas as pd
from src.common import FEATURES, QUALITY_THRESHOLD
from src.drift import psi


def test_quality_gate():
    path = Path(os.getenv('METRICS_FILE', 'metrics.json'))
    metrics = json.loads(path.read_text(encoding='utf-8'))
    assert metrics['f1'] >= QUALITY_THRESHOLD, f"F1={metrics['f1']:.3f} < {QUALITY_THRESHOLD:.2f}"


def test_model_smoke():
    model = joblib.load('models/model.joblib')
    sample = pd.read_csv('data/processed/test.csv').iloc[:2]
    assert len(model.predict(sample[FEATURES])) == 2
    assert model.predict_proba(sample[FEATURES]).shape == (2, 2)


def test_drift_detector_on_known_cases():
    ref = list(range(100))
    assert psi(ref, ref) == 0
    assert psi(ref, [x + 100 for x in ref]) > 0.2
