import csv
import hashlib
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .collection.api import create_collection_router
from .collection.repository import CollectionRepository
from .collection.service import CollectionService
from .domain import ImportBody, ProjectBody, RevisionBody, SchemaBody, parse_dataset, preset_criteria
from .research import NOTES, Research
from .store import Store

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def create_app(
    db_path: Path | None = None,
    research_dir: Path | None = None,
    collection_service_factory=None,
):
    database_path = db_path or Path(os.environ.get('NEV_DB_PATH', ROOT / '.runtime/platform.sqlite3'))
    store = Store(database_path)
    research = Research(research_dir or ROOT / 'backend/data/research')
    collection_repository = CollectionRepository(database_path)
    collection_service = (
        collection_service_factory(collection_repository)
        if collection_service_factory is not None
        else CollectionService(collection_repository)
    )

    @asynccontextmanager
    async def lifespan(application):
        collection_repository.pause_interrupted_jobs(now())
        try:
            yield
        finally:
            collection_service.shutdown()

    app = FastAPI(
        title='新能源汽车情景多准则决策分析系统',
        version='0.1.0',
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.collection_repository = collection_repository
    app.state.collection_service = collection_service
    with store.connect() as conn:
        conn.execute('INSERT OR IGNORE INTO projects VALUES (?,?,?,?)',
                     ('research-archive', '新能源汽车消费者决策研究', 'preset', now()))
        conn.execute('INSERT OR IGNORE INTO schemas VALUES (?,?,?,?,?,?,?)',
                     ('preset-v1', 'research-archive', 1, 'frozen', 1, encoded(preset_criteria()), now()))

    def project_and_schema(project_id, schema_id=None):
        with store.connect() as conn:
            project = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if project is None:
                raise HTTPException(404, '项目不存在')
            if schema_id:
                schema = conn.execute('SELECT * FROM schemas WHERE id=? AND project_id=?', (schema_id, project_id)).fetchone()
            else:
                schema = conn.execute('SELECT * FROM schemas WHERE project_id=? ORDER BY version DESC LIMIT 1', (project_id,)).fetchone()
            if schema is None:
                raise HTTPException(404, '当前项目没有该准则版本')
            return dict(project), store.schema(schema)

    def dataset_for(project, schema):
        if project['mode'] == 'preset':
            return research.records, {'name': '原研究加工数据', 'id': 'research-archive',
                                      'sha256': research.manifest['files']['data/processed/data_optimized.csv']}
        with store.connect() as conn:
            row = conn.execute('SELECT * FROM datasets WHERE project_id=? AND schema_id=? ORDER BY created_at DESC LIMIT 1',
                               (project['id'], schema['id'])).fetchone()
        if row is None:
            return [], None
        return json.loads(row['records']), {k: row[k] for k in ['id', 'name', 'sha256', 'created_at']}

    def context(project_id, schema_id=None):
        project, schema = project_and_schema(project_id, schema_id)
        records, dataset = dataset_for(project, schema)
        months = sorted({r['month'] for r in records})
        return project, schema, records, dataset, months

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0', 'app_id': 'nev-mcdm-platform'}

    app.include_router(create_collection_router(collection_repository, collection_service))

    @app.get('/api/projects')
    def projects():
        with store.connect() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM projects ORDER BY created_at,id')]

    @app.post('/api/projects', status_code=201)
    def create_project(body: ProjectBody):
        project_id, schema_id = str(uuid4()), str(uuid4())
        date = now()
        with store.connect() as conn:
            conn.execute('INSERT INTO projects VALUES (?,?,?,?)', (project_id, body.name, body.mode, date))
            conn.execute('INSERT INTO schemas VALUES (?,?,?,?,?,?,?)',
                         (schema_id, project_id, 1, 'frozen' if body.mode == 'preset' else 'draft',
                          1, encoded(preset_criteria()), date))
        return {'id': project_id, 'name': body.name, 'mode': body.mode, 'created_at': date}

    @app.get('/api/projects/{project_id}/schemas')
    def schemas(project_id: str):
        project_and_schema(project_id)
        with store.connect() as conn:
            return [store.schema(row) for row in conn.execute('SELECT * FROM schemas WHERE project_id=? ORDER BY version DESC', (project_id,))]

    @app.put('/api/projects/{project_id}/schemas/{schema_id}')
    def save_schema(project_id: str, schema_id: str, body: SchemaBody):
        project, _ = project_and_schema(project_id, schema_id)
        if project['mode'] != 'custom':
            raise HTTPException(409, '预置研究的准则只读，请新建自定义项目')
        with store.connect() as conn:
            count = conn.execute("UPDATE schemas SET criteria=?, revision=revision+1 WHERE id=? AND project_id=? AND status='draft' AND revision=?",
                                 (encoded([c.model_dump() for c in body.criteria]), schema_id, project_id, body.revision)).rowcount
            if count != 1:
                raise HTTPException(409, '准则已冻结或被其他窗口修改，请刷新后重试')
            return store.schema(conn.execute('SELECT * FROM schemas WHERE id=?', (schema_id,)).fetchone())

    @app.post('/api/projects/{project_id}/schemas/{schema_id}/freeze')
    def freeze_schema(project_id: str, schema_id: str, body: RevisionBody):
        project_and_schema(project_id, schema_id)
        with store.connect() as conn:
            count = conn.execute("UPDATE schemas SET status='frozen', revision=revision+1 WHERE id=? AND project_id=? AND status='draft' AND revision=?",
                                 (schema_id, project_id, body.revision)).rowcount
            if count != 1:
                raise HTTPException(409, '版本已冻结或已被修改，请刷新')
            return store.schema(conn.execute('SELECT * FROM schemas WHERE id=?', (schema_id,)).fetchone())

    @app.post('/api/projects/{project_id}/schemas/{schema_id}/fork', status_code=201)
    def fork_schema(project_id: str, schema_id: str):
        project, schema = project_and_schema(project_id, schema_id)
        if project['mode'] != 'custom':
            raise HTTPException(409, '请新建自定义项目以编辑准则')
        if schema['status'] != 'frozen':
            raise HTTPException(409, '请先完成当前草稿，再派生新版本')
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT 1 FROM schemas WHERE project_id=? AND status='draft'", (project_id,)).fetchone():
                raise HTTPException(409, '此项目已有草稿版本，请先处理该草稿')
            version = conn.execute('SELECT MAX(version) FROM schemas WHERE project_id=?', (project_id,)).fetchone()[0] + 1
            new_id = str(uuid4())
            conn.execute('INSERT INTO schemas VALUES (?,?,?,?,?,?,?)',
                         (new_id, project_id, version, 'draft', 1, encoded(schema['criteria']), now()))
            return store.schema(conn.execute('SELECT * FROM schemas WHERE id=?', (new_id,)).fetchone())

    @app.get('/api/projects/{project_id}/overview')
    def overview(project_id: str, schema_id: str | None = None):
        project, schema, records, dataset, months = context(project_id, schema_id)
        source_labels = {c['criterion']: c['ordinal_labels'] for c in research.source_criteria}
        return {'project': project, 'schema': schema, 'dataset': dataset, 'months': months,
                'stats': {'records': len(records), 'models': len({r['model'] for r in records}),
                          'months': len(months), 'criteria': len(schema['criteria'])},
                'prediction_months': sorted({r['month'] for r in research.predictions}) if project['mode'] == 'preset' else [],
                'source_labels': source_labels if project['mode'] == 'preset' else {},
                'notes': NOTES if project['mode'] == 'preset' else ['自定义准则项目。数据与模型按准则版本隔离；本阶段尚未接入训练。'],
                'source': research.manifest if project['mode'] == 'preset' else None}

    @app.get('/api/projects/{project_id}/data')
    def data(project_id: str, schema_id: str | None = None, month: str | None = None,
             search: str = '', page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=100)):
        _, _, records, _, months = context(project_id, schema_id)
        selected = month or (months[-1] if months else None)
        rows = [r for r in records if r['month'] == selected]
        total_sales = sum(r['sales'] for r in rows)
        all_count = len(rows)
        rows = sorted([r for r in rows if search.casefold() in r['model'].casefold()], key=lambda r: (-r['share'], r['model']))
        return {'rows': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page,
                'month': selected, 'month_models': all_count, 'month_total_sales': total_sales}

    @app.post('/api/projects/{project_id}/schemas/{schema_id}/datasets', status_code=201)
    def import_dataset(project_id: str, schema_id: str, body: ImportBody):
        project, schema = project_and_schema(project_id, schema_id)
        if project['mode'] != 'custom' or schema['status'] != 'frozen':
            raise HTTPException(409, '请在自定义项目中冻结准则，再导入匹配的数据')
        try:
            records = parse_dataset(body.csv_text, schema['criteria'])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        dataset_id = str(uuid4())
        digest = hashlib.sha256(body.csv_text.encode('utf-8')).hexdigest()
        with store.connect() as conn:
            conn.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?,?)',
                         (dataset_id, project_id, schema_id, body.name, digest, encoded(records), now()))
        return {'id': dataset_id, 'records': len(records), 'sha256': digest}

    @app.get('/api/projects/{project_id}/curves')
    def curves(project_id: str, kind: Literal['weights', 'rationality'] = 'weights'):
        project, _ = project_and_schema(project_id)
        return {'rows': research.curves(kind) if project['mode'] == 'preset' else [],
                'kind': kind, 'source': '归档后处理报表', 'notes': NOTES if project['mode'] == 'preset' else []}

    @app.get('/api/projects/{project_id}/predictions')
    def predictions(project_id: str, month: str | None = None):
        project, _ = project_and_schema(project_id)
        rows = [r for r in research.predictions if r['month'] == month] if project['mode'] == 'preset' else []
        return {'rows': sorted(rows, key=lambda r: -r['actual']), 'source': '原研究归档条件份额估计', 'notes': NOTES if rows else []}

    @app.get('/api/projects/{project_id}/experiments')
    def experiments(project_id: str):
        project, _ = project_and_schema(project_id)
        return research.experiments() if project['mode'] == 'preset' else {'baseline': [], 'ablation': [], 'notes': []}

    @app.get('/api/projects/{project_id}/export')
    def export(project_id: str, kind: Literal['dataset', 'report', 'template'] = 'report', schema_id: str | None = None):
        project, schema, records, dataset, months = context(project_id, schema_id)
        if kind == 'report':
            payload = {'exported_at': now(), **overview(project_id, schema_id),
                       'curves': research.curves('weights') if project['mode'] == 'preset' else [],
                       'predictions': research.predictions if project['mode'] == 'preset' else [],
                       'experiments': experiments(project_id)}
            return Response(encoded(payload), media_type='application/json',
                            headers={'Content-Disposition': 'attachment; filename="research-report.json"'})
        if kind == 'dataset' and not records:
            raise HTTPException(404, '当前准则版本尚未导入数据')
        output = io.StringIO()
        fields = ['产品型号', '观察区间', '时间压力', 'Real_Sales', *[c['name'] for c in schema['criteria']]]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        if kind == 'dataset':
            for r in records:
                # Prevent spreadsheet formula execution in exported text cells.
                model = r['model']
                if model.startswith(('=', '+', '-', '@', '\t', '\r')):
                    model = "'" + model
                writer.writerow({'产品型号': model, '观察区间': r['month'], '时间压力': r['pressure'], 'Real_Sales': r['sales'],
                                 **{c['name']: encoded({f'L{i}': v for i, v in enumerate(r['probabilities'][c['name']])}) for c in schema['criteria']}})
        return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{kind}.csv"'})

    dist = ROOT / 'frontend/dist'
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    def index():
        if not (dist / 'index.html').is_file():
            raise HTTPException(503, '请先构建前端，或启动Vite开发服务')
        return FileResponse(dist / 'index.html')

    return app
