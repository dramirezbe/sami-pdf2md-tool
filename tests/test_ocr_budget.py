from __future__ import annotations

import sys
import threading
import time
import types
from types import SimpleNamespace

import pytest

from sami.ocr_budget import PageBudget, _partial_page_html, _stream_generation, bounded_ocr, page_seconds


class GenerationResult:
    def __init__(self, raw, token_count, error=False, mean_token_prob=None, logprobs=None):
        self.raw, self.token_count, self.error = raw, token_count, error
        self.mean_token_prob, self.logprobs = mean_token_prob, logprobs


@pytest.fixture
def schema(monkeypatch):
    monkeypatch.setitem(sys.modules, "surya.inference.schema", SimpleNamespace(GenerationResult=GenerationResult))


def make_item():
    return SimpleNamespace(prompt=None, prompt_type="high_accuracy_bbox", image=None,
        max_tokens=None, temperature=None, top_p=None, request_logprobs=False,
        guided_json=None, guided_regex=None)


def helpers():
    return SimpleNamespace(PROMPT_MAPPING={"high_accuracy_bbox": "prompt"}, scale_to_fit=lambda x: x,
        _build_messages=lambda *_: [], _mean_token_prob=lambda x: None)


def chunk(text=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text),
        finish_reason=finish, logprobs=None)])


def test_stream_timeout_retains_text_and_closes(schema):
    unblocked = threading.Event()
    class Stream:
        def __iter__(self):
            yield chunk("partial")
            unblocked.wait(2)
            yield chunk("late")
        def close(self):
            unblocked.set()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: Stream())))
    budget = PageBudget(3, .05)
    started = time.monotonic()
    result = _stream_generation(make_item(), client, "model", 100, 0, .1, 5, False, budget, helpers())
    assert time.monotonic() - started < .5
    assert result.raw == "partial" and not result.error and budget.timed_out
    assert unblocked.wait(1)


def test_finished_stream_reports_truncation(schema):
    class Stream:
        def __iter__(self):
            return iter([chunk("text"), chunk(finish="length")])
        def close(self):
            pass
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: Stream())))
    budget = PageBudget(1, 3)
    result = _stream_generation(make_item(), client, "model", 100, 0, .1, 5, False, budget, helpers())
    assert result.raw == "text" and not budget.timed_out and budget.truncated == 1


def test_partial_html_preserves_text_when_no_valid_block():
    assert "unfinished &amp;" in _partial_page_html("unfinished &", lambda _: [])
    assert _partial_page_html("valid", lambda _: [object()]) == "valid"


def test_page_timeout_configuration(monkeypatch):
    monkeypatch.setenv("SAMI_OCR_PAGE_TIMEOUT", "2.5")
    assert page_seconds() == 2.5
    for bad in ("0", "-1", "NaN", "inf", "oops"):
        monkeypatch.setenv("SAMI_OCR_PAGE_TIMEOUT", bad)
        with pytest.raises(ValueError):
            page_seconds()


def test_page_budgets_are_separate_and_hooks_are_restored(monkeypatch):
    backend = types.ModuleType("surya.inference.backends.openai_client")
    backend._generate_one = lambda *_a, **_kw: GenerationResult("original", 1)
    backend._should_retry = lambda *_a, **_kw: False
    parent = types.ModuleType("surya.inference.backends")
    parent.openai_client = backend
    recognition = types.ModuleType("surya.recognition")
    recognition._detect_repeat_loop = lambda *_a: False
    recognition.parse_full_page_html = lambda raw: [raw] if raw.startswith("<div") else []
    seen = []

    class Predictor:
        def __call__(self, images, layout_results=None, *, full_page=None):
            seen.append((images, layout_results))
            item = make_item()
            result = backend._generate_one(item, None, "model", 100, 0, .1, 5, False)
            backend._should_retry(result, 0, 3)
            return [result.raw]

    recognition.RecognitionPredictor = Predictor
    for name, module in {"surya": types.ModuleType("surya"),
                         "surya.inference": types.ModuleType("surya.inference"),
                         "surya.inference.backends": parent,
                         "surya.recognition": recognition}.items():
        monkeypatch.setitem(sys.modules, name, module)
    original = Predictor.__call__
    calls = []
    def generation(_item, _client, _model, _tokens, _temp, _top_p, _timeout, _logprobs, budget, _helpers):
        calls.append(budget.page)
        if budget.page == 4:
            budget.timed_out = True
            return GenerationResult("incomplete &", 1)
        return GenerationResult("<div>ok</div>", 1)
    monkeypatch.setattr("sami.ocr_budget._stream_generation", generation)
    reports = []
    with bounded_ocr([4, 9], lambda budget, elapsed: reports.append(budget), seconds=2):
        output = Predictor()(["first", "second"], ["a", "b"], full_page=True)
    assert calls == [4, 9]
    assert seen == [(["first"], ["a"]), (["second"], ["b"])]
    assert "incomplete &amp;" in output[0]
    assert output[1] == "<div>ok</div>"
    assert [report.timed_out for report in reports] == [True, False]
    assert Predictor.__call__ is original
    calls.clear()
    reports.clear()
    with bounded_ocr([], lambda budget, elapsed: reports.append(budget), seconds=2,
                     block_page_numbers=[4, 9]):
        Predictor()(["first", "second"], ["a", "b"], full_page=False)
    assert calls == [4, 9]
    assert [report.page for report in reports] == [4, 9]
