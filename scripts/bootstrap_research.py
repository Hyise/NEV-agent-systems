"""Copy an explicit allowlist from the supplied research ZIP; never execute it."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = [
    'data/processed/data_optimized.csv', 'data/processed/weights.csv',
    'data/processed/rationality.csv', 'data/processed/pns_deltas.csv',
    'data/results/test_set_predictions.csv', 'data/results/baseline_results.csv',
    'data/results/ablation_final.csv', 'final_criteria_definition_fixed.json',
]


def bootstrap(archive_path: Path):
    target = ROOT / 'backend/data/research'
    if (target / 'manifest.json').exists():
        raise SystemExit('研究归档已存在；不会覆盖。需要升级时请建立新的研究版本。')
    with zipfile.ZipFile(archive_path) as archive:
        prefix = 'llm-beast-mcdm/'
        files = {name: archive.read(prefix + name) for name in DATA_FILES}
        reference = {}
        for item in archive.infolist():
            name = item.filename.removeprefix(prefix)
            if '..' in Path(name).parts or name.startswith(('/', '\\')):
                raise ValueError('Unsafe archive path')
            if (name.startswith(('src/', 'scripts/', 'configs/', 'prompts/'))
                and name.endswith(('.py', '.yaml', '.txt'))) or name in ('README.md', 'requirements.txt'):
                reference[name] = archive.read(item)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (target / Path(name).name).write_bytes(data)
    for name, data in reference.items():
        dest = ROOT / 'algorithms/reference' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    manifest = {
        'archive_name': archive_path.name,
        'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        'source': '用户提供的原研究归档；本系统未重训',
        'evaluation_status': 'historical_unvalidated',
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'已归档 {len(files)} 个数据文件、{len(reference)} 个参考源码文件。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    bootstrap(parser.parse_args().archive)
