import asyncio
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace as NS
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('structured_qa', ROOT/'structured_qa.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def fixture(failure=False, empty=False):
    tables = {
        'text_units': pd.DataFrame([{'id':'stable-unit', 'human_readable_id':7, 'document_id':'DOC-test'}]),
        'documents': pd.DataFrame([{'id':'DOC-test','title':'Test document','raw_data':{'source_file':'raw.txt'}}]),
    }
    context = NS(context_chunks='EXACT RETRIEVED CONTEXT', context_records={'sources': pd.DataFrame([] if empty else [{'id':'7','text':'Retrieved source text'}])})
    class Builder:
        def __init__(self): self.calls = 0
        def build_context(self, **kwargs): self.calls += 1; return context
    class Model:
        async def completion_async(self, **kwargs):
            if failure(kwargs['messages'][-1]['content']) if callable(failure) else failure:
                raise TimeoutError('provider error with potentially sensitive details')
            async def chunks():
                yield NS(choices=[NS(delta=NS(content='Test answer'),finish_reason=None)],usage=None)
                yield NS(choices=[NS(delta=NS(content=''),finish_reason='stop')],usage=None)
                yield NS(choices=[],usage=NS(model_dump=lambda:{'total_tokens':12}))
            return chunks()
    class Engine:
        def __init__(self): self.context_builder=Builder(); self.model=Model()
        async def search(self, query):
            c=self.context_builder.build_context(query=query)
            messages=[{'role':'system','content':'PROMPT\n'+c.context_chunks},{'role':'user','content':query}]
            try:
                stream=await self.model.completion_async(messages=messages,stream=True)
                response=''
                async for chunk in stream: response+=chunk.choices[0].delta.content or ''
            except Exception:
                # The installed LocalSearch also returns an empty response on generation failure.
                response=''
            return NS(response=response,prompt_tokens=10,output_tokens=2)
    return Engine(), tables


class StructuredTests(unittest.TestCase):
    def test_inference_rejects_gold_and_duplicate_ids(self):
        cases=[[{'id':'q','question':'q','answer':'GOLD'}],[{'id':'q','question':'q'},{'id':'q','question':'q2'}]]
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            p=Path(folder)/'questions.json'
            for rows in cases:
                p.write_text(json.dumps(rows))
                with self.assertRaises(qa.ConfigurationError): qa.load_questions(p)

    def test_exact_context_trace_and_source_mapping(self):
        engine,tables=fixture(); original=engine.context_builder
        result=asyncio.run(qa.answer_question(engine,tables,{'id':'q','question':'Question'},{}))
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['context'],['EXACT RETRIEVED CONTEXT'])
        self.assertIn(result['context'][0],result['generation_messages'][0]['content'])
        self.assertEqual(result['sources'][0]['doc_id'],'DOC-test')
        self.assertEqual(result['sources'][0]['text_unit_id'],'stable-unit')
        self.assertEqual(result['generation_usage'],{'total_tokens':12})
        self.assertEqual(original.calls,1)
        self.assertIs(engine.context_builder,original)

    def test_generation_failure_keeps_context_without_exception_details(self):
        engine,tables=fixture(failure=True)
        result=asyncio.run(qa.answer_question(engine,tables,{'id':'q','question':'Question'},{}))
        self.assertEqual(result['status'],'generation_error')
        self.assertEqual(result['generated_answer'],'')
        self.assertEqual(result['context'],['EXACT RETRIEVED CONTEXT'])
        self.assertEqual(result['error'],'TimeoutError')
        self.assertNotIn('sensitive',json.dumps(result))

    def test_no_context_skips_generation(self):
        engine,tables=fixture(empty=True)
        result=asyncio.run(qa.answer_question(engine,tables,{'id':'q','question':'Question'},{}))
        self.assertEqual(result['status'],'no_context')
        self.assertEqual(result['context'],[])
        self.assertEqual(result['llm_calls'],0)

    def test_batch_failure_continues_and_existing_results_are_protected(self):
        (ROOT/'outputs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'outputs') as folder:
            base=Path(folder)
            questions=base/'questions.json'
            questions.write_text(json.dumps([{'id':'failed','question':'fail'},{'id':'good','question':'pass'}]))
            output=base/'predictions.json'
            args=NS(questions=str(questions),output=str(output),scope='smoke',community_level=0)
            engine,tables=fixture(failure=lambda question: question=='fail')
            with patch.object(qa,'make_engine',return_value=(engine,tables,{},{})) as factory:
                self.assertEqual(asyncio.run(qa.run(args)),2)
                rows=json.loads(output.read_text())
                self.assertEqual([r['status'] for r in rows],['generation_error','ok'])
                self.assertTrue(rows[0]['context'])
                state=json.loads(output.with_suffix('.run.json').read_text())
                self.assertEqual((state['state'],state['expected_n'],state['completed_n']),('complete_with_errors',2,2))
                before=output.read_bytes()
                with self.assertRaises(qa.ConfigurationError): asyncio.run(qa.run(args))
                self.assertEqual(output.read_bytes(),before)
                self.assertEqual(factory.call_count,1)

    def test_unfinished_reasoning_is_not_a_final_answer(self):
        with self.assertRaises(ValueError): qa.final_answer('<think>unfinished')
        self.assertEqual(qa.final_answer('<think>hidden</think>Final'),'Final')

if __name__=='__main__': unittest.main()
