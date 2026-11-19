from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split

data = pd.read_csv('data/raw.csv')
train_val, test = train_test_split(data, test_size=0.2, random_state=42, stratify=data['dropout'])
train, validation = train_test_split(train_val, test_size=0.25, random_state=42, stratify=train_val['dropout'])
output = Path('data/processed')
output.mkdir(parents=True, exist_ok=True)
for name, frame in [('train', train), ('validation', validation), ('test', test)]:
    frame.to_csv(output / f'{name}.csv', index=False)
    print(name, len(frame))
