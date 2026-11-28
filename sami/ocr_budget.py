"""Bound local Surya OCR per page and retain streamed partial text.

Surya's OpenAI client normally buffers responses and retries internally. These
hooks are limited to Marker's OCR stage; layout and table inference are left
alone. A timed-out page is explicitly reported as incomplete.
"""
from __future__ import annotations

import contextlib
import html
import os
import threading
import time
from dataclasses import dataclass, field

DEFAULT_PAGE_SECONDS = 120.0


@dataclass
class PageBudget:
    page: int | None
    seconds: float
    started: float = field(default_factory=time.monotonic)
    retries: int = 0
    truncated: int = 0
    timed_out: bool = False
    previous_text: dict[int, str] = field(default_factory=dict)

    def remaining(self):
        return max(0.0, self.seconds - (time.monotonic() - self.started))


def page_seconds():
    value = os.environ.get("SAMI_OCR_PAGE_TIMEOUT", str(DEFAULT_PAGE_SECONDS))
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError("SAMI_OCR_PAGE_TIMEOUT must be a positive number of seconds") from exc
    if not 0 < result < float("inf"):
        raise ValueError("SAMI_OCR_PAGE_TIMEOUT must be a positive number of seconds")
    return result


def _stream_generation(item, client, model_name, max_tokens_default, temperature,
                       top_p, timeout, request_logprobs_default, budget, helpers):
    """Read streamed chunks until the page deadline, keeping received content."""
    from surya.inference.schema import GenerationResult

    if budget.remaining() <= 0:
        budget.timed_out = True
        return GenerationResult(raw="", token_count=0, error=False)
    prompt = item.prompt or helpers.PROMPT_MAPPING[item.prompt_type]
    image = helpers.scale_to_fit(item.image)
    kwargs = {
        "model": model_name, "messages": helpers._build_messages(image, prompt),
        "max_tokens": item.max_tokens or max_tokens_default,
        "temperature": item.temperature if item.temperature is not None else temperature,
        "top_p": item.top_p if item.top_p is not None else top_p,
        "timeout": min(timeout, max(budget.remaining(), 0.001)), "stream": True,
    }
    if item.request_logprobs or request_logprobs_default:
        kwargs["logprobs"] = True
    if item.guided_json is not None:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "structured_output", "schema": item.guided_json, "strict": True}}
    if item.guided_regex is not None:
        kwargs["extra_body"] = {"guided_regex": item.guided_regex}

    lock, finished = threading.Lock(), threading.Event()
    state = {"text": [], "logprobs": [], "stream": None, "error": None, "finish": None}

    def consume():
        try:
            stream = client.chat.completions.create(**kwargs)
            with lock:
                state["stream"] = stream
            # If the deadline expired while connecting, close immediately.
            if finished.is_set():
                stream.close()
                return
            try:
                for chunk in stream:
                    with lock:
                        if finished.is_set():
                            break
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        text = getattr(choice.delta, "content", None)
                        if text:
                            state["text"].append(text)
                        if getattr(choice, "finish_reason", None):
                            state["finish"] = choice.finish_reason
                        lp = getattr(choice, "logprobs", None)
                        for token in getattr(lp, "content", None) or []:
                            state["logprobs"].append(token.model_dump() if hasattr(token, "model_dump") else token)
            finally:
                stream.close()
        except Exception as exc:
            with lock:
                state["error"] = exc
        finally:
            finished.set()

    threading.Thread(target=consume, name="sami-ocr-stream", daemon=True).start()
    completed = finished.wait(budget.remaining())
    with lock:
        if not completed:
            budget.timed_out = True
            finished.set()
        raw = "".join(state["text"])
        logs = list(state["logprobs"])
        stream, error, reason = state["stream"], state["error"], state["finish"]
    if not completed and stream is not None:
        # A read can be blocked in httpx. Close without delaying the next page;
        # its configured HTTP timeout also bounds an unresponsive connection.
        threading.Thread(target=stream.close, name="sami-ocr-close", daemon=True).start()
    if reason == "length":
        budget.truncated += 1
    return GenerationResult(raw=raw, token_count=len(logs),
                            error=bool(error and not budget.timed_out),
                            mean_token_prob=helpers._mean_token_prob(logs), logprobs=logs or None)


def _partial_page_html(raw, parse):
    """Provide parseable page HTML even when a response ended mid-tag."""
    try:
        if raw and parse(raw):
            return raw
    except Exception:
        pass
    # Preserve any text that cannot be parsed as structured blocks. The gap
    # warning makes clear that the page needs review.
    return '<div data-bbox="0 0 1000 1000" data-label="Text">' + html.escape(raw) + '</div>'


@contextlib.contextmanager
def bounded_ocr(page_numbers, report, *, seconds=None, block_page_numbers=()):
    """Apply an end-to-end budget separately to each page in Marker's OCR."""
    from surya.inference.backends import openai_client
    import surya.recognition as recognition

    limit = page_seconds() if seconds is None else seconds
    original_call = recognition.RecognitionPredictor.__call__
    original_generate = openai_client._generate_one
    original_retry = openai_client._should_retry
    original_repeat = recognition._detect_repeat_loop
    active = [None]
    full_page_numbers = list(page_numbers)
    block_numbers = list(block_page_numbers)
    first_full_page_call = [True]
    first_block_page_call = [True]

    def generate(item, client, model_name, max_tokens_default, temperature, top_p,
                 timeout, request_logprobs_default):
        budget = active[0]
        if budget is None:
            return original_generate(item, client, model_name, max_tokens_default, temperature,
                                     top_p, timeout, request_logprobs_default)
        result = _stream_generation(item, client, model_name, max_tokens_default, temperature,
                                    top_p, timeout, request_logprobs_default, budget, openai_client)
        previous = budget.previous_text.get(id(item), "")
        if budget.timed_out and not result.raw:
            result.raw = previous
        elif result.raw and not result.error:
            budget.previous_text[id(item)] = result.raw
        if budget.timed_out and item.prompt_type == "high_accuracy_bbox":
            result.raw = _partial_page_html(result.raw, recognition.parse_full_page_html)
        return result

    def should_retry(result, retries, max_retries):
        budget = active[0]
        if budget and (budget.timed_out or budget.remaining() <= 0):
            budget.timed_out = True
            return False
        retry = original_retry(result, retries, max_retries)
        if budget and retry:
            budget.retries += 1
        return retry

    def repeat(text, *args, **kwargs):
        # The retained partial text must not trigger an unbounded fallback.
        if active[0] and active[0].timed_out:
            return False
        return original_repeat(text, *args, **kwargs)

    def call(self, images, layout_results=None, *, full_page=None):
        if active[0] is not None or not images:
            return original_call(self, images, layout_results, full_page=full_page)
        numbered_full = bool(full_page and first_full_page_call[0])
        numbered_blocks = bool(full_page is False and first_block_page_call[0])
        if numbered_full:
            first_full_page_call[0] = False
        if numbered_blocks:
            first_block_page_call[0] = False
        numbers = full_page_numbers if numbered_full else block_numbers if numbered_blocks else []
        outputs = []
        for index, image in enumerate(images):
            page = numbers[index] if index < len(numbers) else None
            budget = PageBudget(page=page, seconds=limit)
            active[0] = budget
            try:
                layouts = [layout_results[index]] if layout_results is not None else None
                outputs.extend(original_call(self, [image], layouts, full_page=full_page))
            finally:
                active[0] = None
                report(budget, time.monotonic() - budget.started)
        return outputs

    recognition.RecognitionPredictor.__call__ = call
    openai_client._generate_one = generate
    openai_client._should_retry = should_retry
    recognition._detect_repeat_loop = repeat
    try:
        yield
    finally:
        recognition.RecognitionPredictor.__call__ = original_call
        openai_client._generate_one = original_generate
        openai_client._should_retry = original_retry
        recognition._detect_repeat_loop = original_repeat
