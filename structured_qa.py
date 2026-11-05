"""Auditable Local Search batch predictions; inference accepts only id/question."""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
PROJECT = Path(__file__).resolve().parent
SCHEMA_VERSION = 'graphrag-predictions-v1'
class ConfigurationError(ValueError):
    pass


RESPONSE_TYPE = '简洁中文回答，先直接回答，再列依据；使用CommonMark段落或列表，不使用表格'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_questions(path):
    rows = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(rows, list) or not rows:
        raise ConfigurationError('Questions must be a nonempty JSON array')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'question'}:
            raise ConfigurationError('Inference accepts exactly id/question; gold fields are forbidden')
        if any(not isinstance(row[k], str) or not row[k].strip() for k in row):
            raise ConfigurationError('Question IDs and questions must be nonempty strings')
        if row['id'] in seen:
            raise ConfigurationError('Duplicate question ID')
        seen.add(row['id'])
    return rows


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def final_answer(raw):
    if '<think>' in raw and '</think>' not in raw:
        raise ValueError('Incomplete reasoning block')
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.S).strip()
    if not text:
        raise ValueError('Empty final answer')
    return text


class NoContextError(Exception):
    pass


class TracedBuilder:
    def __init__(self, delegate):
        self.delegate = delegate
        self.result = None
        self.seconds = 0.0

    def build_context(self, **kwargs):
        start = time.monotonic()
        try:
            self.result = self.delegate.build_context(**kwargs)
            if not any(len(v) for v in self.result.context_records.values()):
                raise NoContextError()
            return self.result
        finally:
            self.seconds = time.monotonic() - start


class TracedModel:
    def __init__(self, delegate):
        self.delegate = delegate
        self.messages = []
        self.raw = ''
        self.usage = None
        self.finish_reasons = []
        self.error = None
        self.seconds = 0.0
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def completion_async(self, *, messages, **kwargs):
        self.messages = json.loads(json.dumps(messages, ensure_ascii=False))
        self.calls += 1
        started = time.monotonic()
        try:
            stream = await self.delegate.completion_async(messages=messages, **kwargs)
        except Exception as exc:
            self.error = type(exc).__name__
            self.seconds += time.monotonic() - started
            raise

        async def captured():
            try:
                async for chunk in stream:
                    usage = getattr(chunk, 'usage', None)
                    if usage is not None:
                        self.usage = usage.model_dump() if hasattr(usage, 'model_dump') else dict(usage)
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    self.raw += choice.delta.content or ''
                    if choice.finish_reason:
                        self.finish_reasons.append(choice.finish_reason)
                    yield chunk
            except Exception as exc:
                self.error = type(exc).__name__
                raise
            finally:
                self.seconds += time.monotonic() - started
        return captured()


def enrich_sources(records, tables):
    units = {str(r['human_readable_id']): r for r in tables['text_units'].to_dict('records')}
    docs = {str(r['id']): r for r in tables['documents'].to_dict('records')}
    sources = []
    for row in records.get('sources', []):
        if row.get('in_context') is False:
            continue
        unit = units.get(str(row['id']))
        doc = docs.get(str(unit['document_id'])) if unit else None
        raw = doc.get('raw_data') or {} if doc else {}
        source = {
            'context_order': len(sources) + 1, 'citation_id': str(row['id']),
            'text_unit_id': unit['id'] if unit else None,
            'doc_id': unit['document_id'] if unit else None,
            'title': doc['title'] if doc else None,
            'source_file': raw.get('source_file'), 'text': row.get('text', ''),
            'retrieval_score': None,
        }
        if unit is None or doc is None:
            source['metadata_error'] = 'SourceIdNotResolved'
        sources.append(source)
    return sources


async def answer_question(engine, tables, item, metadata):
    started = time.monotonic()
    builder, model = TracedBuilder(engine.context_builder), TracedModel(engine.model)
    original_builder, original_model = engine.context_builder, engine.model
    record = {
        'schema_version': SCHEMA_VERSION, **item, 'method': 'local',
        'generated_answer': '', 'raw_response': '', 'context': [],
        'context_text': '', 'context_data': {}, 'context_metadata': [],
        'sources': [], 'retrieved_candidates': None,
        'candidate_recording': 'Not exposed; context_data contains returned context records',
        'generation_messages': [], 'status': 'retrieval_error',
        **metadata,
    }
    result = None
    engine.context_builder, engine.model = builder, model
    try:
        result = await engine.search(query=item['question'])
        if model.error:
            record.update(status='generation_error', error=model.error)
        elif model.finish_reasons and any(r != 'stop' for r in model.finish_reasons):
            record.update(status='generation_error', error='IncompleteCompletion')
        else:
            record.update(generated_answer=final_answer(str(result.response)), status='ok')
    except NoContextError:
        record.update(status='no_context', error='NoContextError')
    except Exception as exc:
        record.update(status='generation_error' if builder.result else 'retrieval_error', error=type(exc).__name__)
    finally:
        engine.context_builder, engine.model = original_builder, original_model
    if builder.result is not None:
        built = builder.result
        records = {k: json.loads(v.to_json(orient='records', force_ascii=False)) for k, v in built.context_records.items()}
        text = str(built.context_chunks)
        sources = enrich_sources(records, tables)
        record.update(context_text=text, context_data=records, sources=sources)
        if record['status'] != 'no_context':
            record['context'] = [text]
            record['context_metadata'] = [{'context_index': 0, 'kind': 'local_mixed_context', 'sources': sources}]
    record.update(
        raw_response=model.raw, generation_messages=model.messages,
        finish_reasons=model.finish_reasons, generation_usage=model.usage,
        latency_seconds=round(time.monotonic() - started, 4),
        retrieval_seconds=round(builder.seconds, 4), generation_seconds=round(model.seconds, 4),
        llm_calls=model.calls,
        token_usage_estimate={k: getattr(result, k, None) for k in ['prompt_tokens', 'output_tokens']},
    )
    if model.messages and record['context']:
        system = next((m.get('content', '') for m in model.messages if m.get('role') == 'system'), '')
        if record['context_text'] not in system:
            raise RuntimeError('Captured context is not in the actual generation request')
    return record


def make_engine(root, community_level):
    import pandas as pd
    from graphrag.config.load_config import load_config
    from graphrag.config.embeddings import entity_description_embedding
    from graphrag.utils.api import get_embedding_store, load_search_prompt
    from graphrag.query.factory import get_local_search_engine
    from graphrag.query.indexer_adapters import read_indexer_entities, read_indexer_reports, read_indexer_text_units, read_indexer_relationships
    status_path = root / 'index-status.json'
    if status_path.exists() and json.loads(status_path.read_text()).get('state') != 'complete':
        raise ConfigurationError('Index status is not complete; this command never starts indexing')
    names = ['entities', 'communities', 'community_reports', 'text_units', 'relationships', 'documents']
    if any(not (root / 'output' / f'{n}.parquet').is_file() for n in names):
        raise ConfigurationError('Required index tables are missing')
    config = load_config(root)
    tables = {n: pd.read_parquet(root / 'output' / f'{n}.parquet') for n in names}
    if any(len(t) == 0 for t in tables.values()):
        raise ConfigurationError('Required index tables must be nonempty')
    prompt = load_search_prompt(config.local_search.prompt)
    engine = get_local_search_engine(
        config=config,
        reports=read_indexer_reports(tables['community_reports'], tables['communities'], community_level),
        text_units=read_indexer_text_units(tables['text_units']),
        entities=read_indexer_entities(tables['entities'], tables['communities'], community_level),
        relationships=read_indexer_relationships(tables['relationships']), covariates={},
        description_embedding_store=get_embedding_store(config=config.vector_store, embedding_name=entity_description_embedding),
        response_type=RESPONSE_TYPE, system_prompt=prompt, callbacks=[],
    )
    model = config.get_completion_model_config(config.local_search.completion_model_id)
    embedding = config.get_embedding_model_config(config.local_search.embedding_model_id)
    index_files = {n: {'size': (root/'output'/f'{n}.parquet').stat().st_size, 'mtime_ns': (root/'output'/f'{n}.parquet').stat().st_mtime_ns} for n in names}
    index_identity = {'root': str(root), 'table_files': index_files}
    for name in ['input/banking.manifest.json', 'settings.yaml']:
        p = root / name
        if p.exists():
            index_identity[name + '_sha256'] = digest(p.read_bytes())
    metadata = {
        'generation_model': model.model, 'embedding_model': embedding.model,
        'index_fingerprint': digest(json.dumps(index_identity, sort_keys=True).encode()),
        'prompt_sha256': digest(prompt.encode()), 'community_level': community_level,
        'generation_parameters': {k: v for k, v in model.call_args.items() if k in ['temperature', 'max_tokens', 'max_completion_tokens', 'timeout']},
    }
    return engine, tables, metadata, index_identity


async def run(args):
    os.umask(0o077)
    questions_path = Path(args.questions).resolve()
    if not questions_path.is_relative_to(PROJECT.parent):
        raise ConfigurationError('Questions must be inside the HippoRAG project tree')
    questions = load_questions(questions_path)
    output = Path(args.output).resolve()
    if not output.is_relative_to(PROJECT / 'outputs') or output.suffix != '.json':
        raise ConfigurationError('Output must be a .json file beneath Microsoft_GraphRAG/outputs')
    manifest_path = output.with_suffix('.run.json')
    if output.exists() or manifest_path.exists():
        raise ConfigurationError('Output already exists; choose a new run directory')
    root = PROJECT / 'smoke' if args.scope == 'smoke' else PROJECT
    engine, tables, metadata, index_identity = make_engine(root, args.community_level)
    output.parent.mkdir(parents=True, exist_ok=True)
    run_info = {
        'schema_version': SCHEMA_VERSION, 'run_scope': args.scope, 'method': 'local',
        'state': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
        'questions_file': str(questions_path), 'questions_sha256': digest(questions_path.read_bytes()),
        'expected_n': len(questions), 'completed_n': 0,
        'output_file': str(output), 'index_identity': index_identity, **metadata,
    }
    atomic_json(manifest_path, run_info)
    records = []
    try:
        for item in questions:
            record = await answer_question(engine, tables, item, {**metadata, 'run_scope': args.scope})
            records.append(record)
            atomic_json(output, records)
            run_info['completed_n'] = len(records)
            atomic_json(manifest_path, run_info)
            print(f"Answered {len(records)}/{len(questions)}: {item['id']} ({record['status']})", flush=True)
    except BaseException:
        run_info.update(state='interrupted_or_error', completed_n=len(records))
        atomic_json(manifest_path, run_info)
        raise
    run_info.update(state='complete' if all(r['status'] == 'ok' for r in records) else 'complete_with_errors', finished_at=datetime.now(timezone.utc).isoformat())
    atomic_json(manifest_path, run_info)
    return 0 if run_info['state'] == 'complete' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['smoke', 'full'], required=True)
    parser.add_argument('--questions', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--community-level', type=int, default=0)
    args = parser.parse_args()
    # Provider failures can embed request details; structured records retain only error classes.
    for name in ['graphrag', 'litellm', 'LiteLLM']:
        logger = logging.getLogger(name)
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
    try:
        code = asyncio.run(run(args))
    except (ConfigurationError, FileNotFoundError) as exc:
        print(f'Configuration error: {exc}', flush=True)
        code = 1
    except Exception as exc:
        print(f'Batch error: {type(exc).__name__}', flush=True)
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()
