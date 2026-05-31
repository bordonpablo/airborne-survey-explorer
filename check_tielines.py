import pandas as pd
from pathlib import Path

pq = next(Path('data/interim').rglob('*_m02.parquet'))
df = pd.read_parquet(pq)
if 'Yaw' in df.columns and 'line_id' in df.columns:
    on = df[df['line_id'].notna() & df['line_valid']]
    dirs = on.groupby('line_id')['Yaw'].mean().apply(
        lambda y: 'NS' if (y < 45 or y > 315 or (135 < y < 225)) else 'EW'
    )
    print(dirs.value_counts())
