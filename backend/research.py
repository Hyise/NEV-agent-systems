"""Read-only adapter. All predictions below are historical artifacts, not inference."""
import csv
import hashlib
import io
import json
from pathlib import Path

from .domain import CRITERIA, month_key, parse_dataset, preset_criteria

NOTES = [
    '当前预测与实验指标来自原研究归档，本系统未重新训练。',
    '原训练脚本覆盖全部月份；最后两个月的归档指标不是严格独立测试结果。',
    '份额分母为当月数据集所含车型的销量总和，不代表全市场口径。',
    '权重曲线来自已平滑报表，理性权重末点还经过趋势修正。',
]


class Research:
    def __init__(self, directory: Path):
        self.directory = directory
        self.manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        for name, digest in self.manifest['files'].items():
            if hashlib.sha256((directory / Path(name).name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'研究归档文件发生变化，请核验来源：{name}')
        self.records = parse_dataset((directory / 'data_optimized.csv').read_text(encoding='utf-8-sig'), preset_criteria())
        self.predictions = [
            {'month': month_key(r['观察区间']), 'model': r['产品型号'].removeprefix('total_'),
             'actual': float(r['真实份额']), 'predicted': float(r['预测份额'])}
            for r in self.read('test_set_predictions.csv')]
        self.source_criteria = json.loads((directory / 'final_criteria_definition_fixed.json').read_text(encoding='utf-8'))['final_criteria']

    def read(self, name):
        return list(csv.DictReader(io.StringIO((self.directory / name).read_text(encoding='utf-8-sig'))))

    def curves(self, kind):
        filename = 'weights.csv' if kind == 'weights' else 'rationality.csv'
        return [{'month': month_key(r['Time']), 'pressure': float(r['Pressure']),
                 'values': {c: float(r[c]) for c in CRITERIA}} for r in self.read(filename)]

    def experiments(self):
        baseline = [{'model': r['model'], **{k: float(r[k]) for k in ['RMSE', 'WAPE', 'R2']}}
                    for r in self.read('baseline_results.csv')]
        ablation = [{'model': r['Model'], **{k: float(r[k]) for k in ['RMSE', 'WAPE', 'R2']}}
                    for r in self.read('ablation_final.csv')]
        return {'baseline': baseline, 'ablation': ablation, 'notes': NOTES}
