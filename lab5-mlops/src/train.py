from pathlib import Path
import json
import joblib
import mlflow
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from common import FEATURES, TARGET

train = pd.read_csv('data/processed/train.csv')
validation = pd.read_csv('data/processed/validation.csv')
mlflow.set_tracking_uri('sqlite:///mlruns.db')
mlflow.set_experiment('online-learning-dropout')
configurations = [
    {'n_estimators': 30, 'max_depth': 4},
    {'n_estimators': 50, 'max_depth': 6},
    {'n_estimators': 70, 'max_depth': 8},
    {'n_estimators': 90, 'max_depth': 12},
    {'n_estimators': 100, 'max_depth': None},
]
results = []
for config in configurations:
    with mlflow.start_run():
        model = RandomForestClassifier(**config, random_state=42, n_jobs=1, class_weight='balanced')
        model.fit(train[FEATURES], train[TARGET])
        score = f1_score(validation[TARGET], model.predict(validation[FEATURES]), zero_division=0)
        mlflow.log_params({**config, 'max_depth': str(config['max_depth']), 'seed': 42})
        mlflow.log_metric('validation_f1', score)
        results.append({'params': config, 'validation_f1': score})
        print(f'{config} validation_f1={score:.4f}')
best = max(results, key=lambda item: item['validation_f1'])
model = RandomForestClassifier(**best['params'], random_state=42, n_jobs=1, class_weight='balanced')
train_val = pd.concat([train, validation], ignore_index=True)
model.fit(train_val[FEATURES], train_val[TARGET])
Path('models').mkdir(exist_ok=True)
Path('reports').mkdir(exist_ok=True)
joblib.dump(model, 'models/model.joblib')
metadata = {'version': 'dropout-rf-v1', 'selected': best, 'seed': 42,
            'features': FEATURES, 'feature_importances': dict(zip(FEATURES, map(float, model.feature_importances_)))}
Path('models/metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
Path('reports/experiments.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print('Selected:', json.dumps(best))
