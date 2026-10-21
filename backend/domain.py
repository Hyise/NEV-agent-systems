"""Strict, model-independent schemas for datasets and ordered criteria."""
import csv
import io
import json
import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CRITERIA = ['空间实用性', '驾驶体验', '续航与能耗可靠性', '智能化体验',
            '内饰品质与健康感知', '外观设计认同度', '成本效益与全周期价值',
            'NVH静谧性', '安全性与被动防护信任', '性价比合理性']
LEVEL_COUNTS = [4, 4, 5, 4, 4, 5, 4, 4, 4, 4]
TIME_PRESSURE_CUTOFF = '2026-01'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Criterion(StrictModel):
    name: str = Field(min_length=1, max_length=50)
    labels: list[str] = Field(min_length=2, max_length=8)

    @field_validator('name')
    @classmethod
    def safe_name(cls, name):
        if name.startswith(('=', '+', '-', '@')) or any(char in name for char in ('\r', '\n')):
            raise ValueError('准则名称不能以公式字符开头或包含换行')
        return name

    @field_validator('labels')
    @classmethod
    def clean_labels(cls, labels):
        labels = [label.strip() for label in labels]
        if any(not label or len(label) > 80 for label in labels):
            raise ValueError('每个等级名称需为1～80个字符')
        if len(labels) != len(set(labels)):
            raise ValueError('同一准则内的等级名称不能重复')
        return labels


class SchemaBody(StrictModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=20)
    revision: int = Field(ge=1)

    @model_validator(mode='after')
    def unique_names(self):
        names = [c.name for c in self.criteria]
        if len(names) != len(set(names)):
            raise ValueError('准则名称不能重复')
        if set(names) & {'产品型号', '观察区间', '时间压力', 'Real_Sales'}:
            raise ValueError('准则名称不能与基础字段重名')
        return self


class ProjectBody(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    mode: Literal['preset', 'custom']


class RevisionBody(StrictModel):
    revision: int = Field(ge=1)


class ImportBody(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    csv_text: str = Field(min_length=1, max_length=8_000_000)


def preset_criteria():
    return [{'name': name, 'labels': [f'L{i}' for i in range(count)]}
            for name, count in zip(CRITERIA, LEVEL_COUNTS)]


def month_key(value: str) -> str:
    parts = [part.strip() for part in value.split('~')]
    if len(parts) not in (1, 2) or (len(parts) == 2 and parts[0] != parts[1]):
        raise ValueError('观察区间必须是单个月份')
    key = parts[0]
    if not re.fullmatch(r'\d{4}-\d{2}', key):
        raise ValueError('月份格式必须为YYYY-MM')
    datetime.strptime(key, '%Y-%m')
    return key


def number(value, name: str, low: float = 0, high: float = math.inf):
    if isinstance(value, bool):
        raise ValueError(f'{name}必须是数字')
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name}必须是数字') from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f'{name}超出允许范围')
    return result


def effective_time_pressure(month: str, value) -> float:
    """Return the research pressure in force for an observation month."""
    if month >= TIME_PRESSURE_CUTOFF:
        return 0.0
    return number(value, '时间压力', 0, 1)


def unique_json_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f'概率等级键重复：{key}')
        obj[key] = value
    return obj


def parse_dataset(text: str, criteria: list[dict]) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required = ['产品型号', '观察区间', '时间压力', 'Real_Sales', *[c['name'] for c in criteria]]
    if not reader.fieldnames or any(key not in reader.fieldnames for key in required):
        raise ValueError('CSV缺少必需字段：' + '、'.join(key for key in required if key not in (reader.fieldnames or [])))
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('CSV列名不能重复')
    records, seen, totals, pressures = [], set(), {}, {}
    for line, row in enumerate(reader, 2):
        try:
            if None in row:
                raise ValueError('列数超出表头，请检查JSON字段的CSV转义')
            model = (row['产品型号'] or '').strip().removeprefix('total_')
            if not model or len(model) > 100:
                raise ValueError('车型名称需为1～100个字符')
            month = month_key(row['观察区间'] or '')
            key = (month, model)
            if key in seen:
                raise ValueError(f'车型月份重复：{month} / {model}')
            seen.add(key)
            pressure = effective_time_pressure(month, row['时间压力'])
            sales = number(row['Real_Sales'], '销量')
            if month in pressures and abs(pressures[month] - pressure) > 1e-6:
                raise ValueError('同月各车型的时间压力必须一致')
            pressures[month] = pressure
            probabilities = {}
            for criterion in criteria:
                values = json.loads(row[criterion['name']], object_pairs_hook=unique_json_pairs)
                keys = [f'L{i}' for i in range(len(criterion['labels']))]
                if not isinstance(values, dict) or set(values) != set(keys):
                    raise ValueError(f"{criterion['name']}等级必须为{'、'.join(keys)}")
                probs = [number(values[key], criterion['name'] + '/' + key, 0, 1) for key in keys]
                if abs(sum(probs) - 1) > 1e-5:
                    raise ValueError(f"{criterion['name']}概率之和必须为1")
                probabilities[criterion['name']] = probs
            totals[month] = totals.get(month, 0) + sales
            records.append({'month': month, 'model': model, 'sales': sales,
                            'pressure': pressure, 'probabilities': probabilities})
            if len(records) > 10_000:
                raise ValueError('本机版每次最多导入10000条车型月份记录')
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f'第{line}行：{exc}') from exc
    if not records:
        raise ValueError('数据集没有记录')
    if any(total <= 0 for total in totals.values()):
        raise ValueError('每个月的总销量必须大于0')
    for row in records:
        row['share'] = row['sales'] / totals[row['month']]
    return records
