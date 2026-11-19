"""Build an independently evaluated second model for a rollout experiment."""
from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from src.common import FEATURES, TARGET, QUALITY_THRESHOLD

train = pd.read_csv('data/processed/train.csv')
validation = pd.read_csv('data/processed/validation.csv')
test = pd.read_csv('data/processed/test.csv')
combined = pd.concat([train, validation], ignore_index=True)
model = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=43,
                               n_jobs=1, class_weight='balanced')
model.fit(combined[FEATURES], combined[TARGET])
score = f1_score(test[TARGET], model.predict(test[FEATURES]), zero_division=0)
if score < QUALITY_THRESHOLD:
    raise SystemExit(f'Second model fails quality gate: F1={score:.4f}')
output = Path('models_v2')
output.mkdir(exist_ok=True)
joblib.dump(model, output / 'model.joblib')
(output / 'metadata.json').write_text(json.dumps({'version': 'dropout-rf-v2',
    'test_f1': score, 'features': FEATURES}, indent=2), encoding='utf-8')
print(json.dumps({'version': 'dropout-rf-v2', 'test_f1': score}))
