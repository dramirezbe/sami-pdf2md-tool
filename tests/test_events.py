from __future__ import annotations

import json
import math
import unittest

from sami.events import Event, EventSequencer, JsonlEventDecoder, encode_jsonl


def event_wire(**overrides):
    value = {
        "protocol_version": 1,
        "event": "job_progress",
        "seq": 1,
        "run_id": "run-研究",
        "job_id": "job 1",
        "attempt": 1,
        "data": {"stage": "解析中", "completed": 2, "total": 5},
    }
    value.update(overrides)
    return value


class EventWireTests(unittest.TestCase):
    def test_unicode_event_round_trip(self) -> None:
        event = Event.from_wire(event_wire())
        self.assertEqual(Event.from_json_line(event.to_json_line()), event)
        self.assertIn("解析中", event.to_json_line())

    def test_unknown_additive_fields_are_ignored(self) -> None:
        wire = event_wire(future_field={"new": True})
        self.assertEqual(Event.from_wire(wire).run_id, "run-研究")

    def test_path_values_in_event_data_are_explicitly_serialized_as_strings(self) -> None:
        from pathlib import Path

        event = Event("job_finished", 1, "run", {"output": Path("/tmp/文書 final.md")})
        wire = event.to_wire()
        self.assertEqual(wire["data"]["output"], "/tmp/文書 final.md")
        self.assertEqual(Event.from_json_line(event.to_json_line()).data["output"], "/tmp/文書 final.md")

    def test_invalid_protocol_fields_are_rejected(self) -> None:
        invalid = (
            {"protocol_version": True},
            {"protocol_version": 1.5},
            {"protocol_version": 2},
            {"seq": True},
            {"seq": 1.5},
            {"seq": 0},
            {"attempt": True},
            {"attempt": 0},
            {"attempt": None},
            {"event": 1},
            {"event": ""},
            {"run_id": None},
            {"job_id": 3},
            {"job_id": ""},
            {"job_id": None},
            {"data": []},
            {"data": None},
            {"data": {1: "not a string key"}},
        )
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                Event.from_wire(event_wire(**change))

    def test_direct_construction_validates_optional_attempt_and_ids(self) -> None:
        for attempt in (0, True, 1.5):
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                Event("job_started", 1, "run", {}, attempt=attempt)  # type: ignore[arg-type]
        for run_id in ("", "  ", 1, None):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                Event("job_started", 1, run_id, {})  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Event("", 1, "run", {})

    def test_nan_and_infinity_are_rejected_on_encode_and_parse(self) -> None:
        for number in (math.nan, math.inf, -math.inf):
            with self.subTest(number=number), self.assertRaises(ValueError):
                Event("metrics", 1, "run", {"value": number})
            raw = json.dumps(event_wire(data={"value": number}))
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Event.from_json_line(raw)
        with self.assertRaises(ValueError):
            Event.from_json_line("NaN")

    def test_sequencer_assigns_increasing_sequence_numbers(self) -> None:
        sequencer = EventSequencer("run")
        self.assertEqual([sequencer.create("warning", {}).seq for _ in range(4)], [1, 2, 3, 4])

    def test_multiple_events_form_jsonl_and_fragmented_utf8_is_buffered(self) -> None:
        events = [
            Event("run_started", 1, "run", {"name": "SAMI"}),
            Event("warning", 2, "run", {"message": "café 文書"}, job_id="job-2", attempt=1),
            Event("run_finished", 3, "run", {"exit_code": 0}),
        ]
        stream = encode_jsonl(events)
        self.assertTrue(stream.endswith(b"\n"))
        self.assertEqual(len(stream.splitlines()), 3)

        decoder = JsonlEventDecoder()
        received = []
        # Split through the multibyte UTF-8 sequence and across JSON records.
        split_at = stream.index("é".encode("utf-8")) + 1
        for fragment in (stream[:split_at], stream[split_at:split_at + 7], stream[split_at + 7:]):
            received.extend(decoder.feed(fragment))
        received.extend(decoder.finish())
        self.assertEqual(received, events)

    def test_decoder_accepts_final_record_without_lf_and_rejects_bad_frames(self) -> None:
        raw = encode_jsonl([Event("done", 1, "run", {})]).rstrip(b"\n")
        decoder = JsonlEventDecoder()
        self.assertEqual(decoder.feed(raw), [])
        self.assertEqual(decoder.finish(), [Event("done", 1, "run", {})])
        with self.assertRaises(ValueError):
            decoder.feed(b"after finish")
        with self.assertRaises(ValueError):
            JsonlEventDecoder().feed(b"\n")
        with self.assertRaises(UnicodeDecodeError):
            decoder = JsonlEventDecoder()
            decoder.feed(b"\xff")


if __name__ == "__main__":
    unittest.main()
