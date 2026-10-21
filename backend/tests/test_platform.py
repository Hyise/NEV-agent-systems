import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite3', ROOT / 'backend/data/research')) as test_client:
        yield test_client


def new_custom(client):
    project = client.post('/api/projects', json={'name': '测试研究', 'mode': 'custom'}).json()
    base = '/api/projects/' + project['id']
    schema = client.get(base + '/schemas').json()[0]
    return base, schema


def freeze(client, base, schema):
    response = client.post(base + f"/schemas/{schema['id']}/freeze", json={'revision': schema['revision']})
    assert response.status_code == 200
    return response.json()


def simple_csv(criteria, overrides=None, duplicate=False):
    stream = io.StringIO()
    fields = ['产品型号', '观察区间', '时间压力', 'Real_Sales', *[c['name'] for c in criteria]]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for model, sales in [('车型甲', 70), ('车型乙', 30)]:
        row = {'产品型号': model, '观察区间': '2025-09', '时间压力': 0.4, 'Real_Sales': sales,
               **{c['name']: json.dumps({f'L{i}': 1 / len(c['labels']) for i in reversed(range(len(c['labels'])))}) for c in criteria}}
        row.update(overrides or {})
        writer.writerow(row)
        if duplicate:
            writer.writerow(row)
    return stream.getvalue()


def import_csv(client, base, schema, text):
    return client.post(base + f"/schemas/{schema['id']}/datasets", json={'name': 'test.csv', 'csv_text': text})


def test_real_archive_and_scope(client):
    overview = client.get('/api/projects/research-archive/overview').json()
    assert overview['stats'] == {'records': 1609, 'models': 132, 'months': 24, 'criteria': 10}
    assert overview['prediction_months'] == ['2025-11', '2025-12']
    assert overview['source']['evaluation_status'] == 'historical_unvalidated'
    assert len(client.get('/api/projects/research-archive/curves').json()['rows']) == 24
    predictions = client.get('/api/projects/research-archive/predictions?month=2024-01').json()['rows']
    assert predictions == []
    predictions = client.get('/api/projects/research-archive/predictions?month=2025-12').json()['rows']
    assert abs(sum(p['predicted'] for p in predictions) - 1) < 1e-5


def test_search_does_not_renormalize(client):
    first = client.get('/api/projects/research-archive/data?month=2025-12').json()
    model = first['rows'][0]['model']
    filtered = client.get('/api/projects/research-archive/data', params={'month': '2025-12', 'search': model}).json()
    assert filtered['rows'][0]['share'] == first['rows'][0]['share']
    assert filtered['month_total_sales'] == first['month_total_sales']


def test_schema_workflow_and_version_isolation(client):
    base, schema = new_custom(client)
    assert client.get(base + '/overview').json()['stats']['records'] == 0
    assert client.get(base + '/predictions?month=2025-12').json()['rows'] == []
    assert import_csv(client, base, schema, simple_csv(schema['criteria'])).status_code == 409
    schema = freeze(client, base, schema)
    result = import_csv(client, base, schema, simple_csv(schema['criteria']))
    assert result.status_code == 201, result.text
    assert client.get(base + '/data?search=车型甲').json()['rows'][0]['share'] == 0.7
    assert client.put(base + '/schemas/' + schema['id'], json={'criteria': schema['criteria'], 'revision': schema['revision']}).status_code == 409
    new_schema = client.post(base + '/schemas/' + schema['id'] + '/fork').json()
    assert new_schema['version'] == 2 and new_schema['status'] == 'draft'
    assert client.get(base + '/overview').json()['stats']['records'] == 0
    assert client.get(base + '/overview?schema_id=' + schema['id']).json()['stats']['records'] == 2
    assert client.post(base + '/schemas/' + schema['id'] + '/fork').status_code == 409


def test_optimistic_revision_and_persistence(client):
    base, schema = new_custom(client)
    body = {'criteria': [{'name': '续航评价', 'labels': ['高', '低']}], 'revision': schema['revision']}
    assert client.put(base + '/schemas/' + schema['id'], json=body).status_code == 200
    assert client.put(base + '/schemas/' + schema['id'], json=body).status_code == 409
    with TestClient(create_app(client.app.state.store.path)) as restarted:
        assert restarted.get(base + '/overview').json()['schema']['criteria'] == body['criteria']


@pytest.mark.parametrize('criteria', [
    [{'name': 'A', 'labels': ['高', '高']}], [{'name': 'A', 'labels': [' ', '低']}],
    [{'name': 'A', 'labels': ['高']}], [{'name': 'A', 'labels': ['高', '低']}, {'name': 'A', 'labels': ['高', '低']}],
    [{'name': 'Real_Sales', 'labels': ['高', '低']}], [{'name': '=CMD()', 'labels': ['高', '低']}],
])
def test_bad_schemas_rejected(client, criteria):
    base, schema = new_custom(client)
    assert client.put(base + '/schemas/' + schema['id'], json={'criteria': criteria, 'revision': 1}).status_code == 422


@pytest.mark.parametrize('overrides', [
    {'Real_Sales': -1}, {'Real_Sales': 'NaN'}, {'Real_Sales': 0},
    {'时间压力': 1.5}, {'观察区间': '2024-13'}, {'观察区间': '2024-01 ~ 2024-02'},
    {'产品型号': ''}, {'空间实用性': '{"L0": 0.3}'},
    {'空间实用性': '{"L0":0.5,"L1":0.5,"L2":0.5,"L3":0.5}'},
    {'空间实用性': '{"L0":0.25,"L0":0.25,"L1":0.25,"L2":0.25,"L3":0.25}'},
])
def test_bad_dataset_rejected_without_mutation(client, overrides):
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)
    assert import_csv(client, base, schema, simple_csv(schema['criteria'], overrides)).status_code == 422
    assert client.get(base + '/overview').json()['stats']['records'] == 0


def test_duplicate_rows_and_month_pressure(client):
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)
    assert import_csv(client, base, schema, simple_csv(schema['criteria'], duplicate=True)).status_code == 422
    text = simple_csv(schema['criteria']).replace('车型乙,2025-09,0.4', '车型乙,2025-09,0.8')
    assert import_csv(client, base, schema, text).status_code == 422


@pytest.mark.parametrize('pressure', ['', '0.8', '1.5', 'not-a-number'])
def test_2026_dataset_treats_time_pressure_as_absent(client, pressure):
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)
    text = simple_csv(
        schema['criteria'],
        {'观察区间': '2026-01', '时间压力': pressure},
    )

    result = import_csv(client, base, schema, text)

    assert result.status_code == 201, result.text
    rows = client.get(base + '/data?month=2026-01').json()['rows']
    assert {row['pressure'] for row in rows} == {0.0}


def test_pre_2026_dataset_still_requires_valid_time_pressure(client):
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)

    result = import_csv(
        client,
        base,
        schema,
        simple_csv(schema['criteria'], {'时间压力': ''}),
    )

    assert result.status_code == 422
    assert '时间压力必须是数字' in result.text


def test_json_key_order_is_canonical(client):
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)
    probs = '{"L3":0.1,"L2":0.2,"L1":0.3,"L0":0.4}'
    assert import_csv(client, base, schema, simple_csv(schema['criteria'], {'空间实用性': probs})).status_code == 201
    assert client.get(base + '/data').json()['rows'][0]['probabilities']['空间实用性'] == [0.4, 0.3, 0.2, 0.1]


def test_preset_is_readonly_and_cross_project_schema_denied(client):
    base, schema = new_custom(client)
    assert client.get('/api/projects/research-archive/overview?schema_id=' + schema['id']).status_code == 404
    assert client.put('/api/projects/research-archive/schemas/preset-v1', json={'revision': 1, 'criteria': schema['criteria']}).status_code == 409


def test_exports_have_provenance_and_roundtrip(client):
    report = client.get('/api/projects/research-archive/export').json()
    assert len(report['source']['archive_sha256']) == 64
    assert report['source']['evaluation_status'] == 'historical_unvalidated'
    assert len(report['predictions']) > 0
    base, schema = new_custom(client)
    schema = freeze(client, base, schema)
    dataset = client.get('/api/projects/research-archive/export?kind=dataset').text
    result = import_csv(client, base, schema, dataset)
    assert result.status_code == 201, result.text
    assert result.json()['records'] == 1609
    assert client.get(base + '/predictions?month=2025-12').json()['rows'] == []


def test_concurrent_drafts_do_not_overwrite(client):
    base, schema = new_custom(client)
    def save(name):
        return client.put(base + '/schemas/' + schema['id'], json={'revision': 1, 'criteria': [{'name': name, 'labels': ['优', '劣']}]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(save, ['A', 'B']))
    assert sorted(statuses) == [200, 409]
