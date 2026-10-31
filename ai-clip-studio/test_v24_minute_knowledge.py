"""Offline tests: no Gemini API key or network required."""
from types import SimpleNamespace
from pathlib import Path
import pytest
import v24_minute_knowledge as v24

@pytest.mark.parametrize('length',[60,90,120])
def test_valid_lengths(length):
    assert v24.check_length(length)==length

@pytest.mark.parametrize('length',[0,10,15,20,30,59,121,-1,'bad'])
def test_never_accept_less_than_60_or_unknown(length):
    with pytest.raises(ValueError): v24.check_length(length)

@pytest.mark.parametrize('requested,actual',[(60,59.99),(90,89.9),(120,118)])
def test_no_short_export(requested,actual):
    with pytest.raises(ValueError):v24.output_gate(actual,requested)

@pytest.mark.parametrize('requested,actual',[(60,60),(90,90),(120,124)])
def test_long_enough_export(requested,actual):
    assert v24.output_gate(actual,requested)

@pytest.mark.parametrize('requested,actual',[(60,45),(90,89),(120,90)])
def test_no_video_replay_for_short_source(requested,actual):
    with pytest.raises(ValueError):v24.footage_gate(actual,requested)


def test_knowledge_prompt_and_source_extraction():
    p=v24.knowledge_prompt('Base editorial', 'สาระน่ารู้',90)
    assert 'Google Search grounding' in p and 'Target 90' in p and 'visual_matches' in p
    assert v24.knowledge_prompt('Original','สารคดี',60)=='Original'
    x={'candidates':[{'groundingMetadata':{'groundingChunks':[
        {'web':{'uri':'https://example.org/science','title':'Science page'}},
        {'web':{'uri':'https://example.org/science','title':'Duplicate'}},
        {'web':{'uri':'javascript:alert(1)','title':'Unsafe'}},
    ]}}]}
    assert v24.evidence_sources(x)==[{'title':'Science page','url':'https://example.org/science'}]
    assert v24.evidence_sources({})==[]
    assert 'at least 120 seconds' in v24.duration_prompt('Old',120)
    assert '19-28' in v24.duration_prompt('Old',120)


def test_workflow_source_is_editable():
    import inspect, v11, v14_semantic, v21_storyflow
    assert 'make_prompt' in inspect.getsource(v14_semantic.analyze_proxy)
    assert 'ns[\'process\']' in inspect.getsource(v11.install)
    assert 'natural_voice' in inspect.getsource(v21_storyflow.install)
