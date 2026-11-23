from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from sami.contracts import (
    ConversionOptions,
    ConversionRequest,
    EngineResult,
    JobResult,
    RecoveredReference,
    RunResult,
)


class ContractWireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.gettempdir()) / "SAMI papers 研究"
        self.input_path = self.root / "研究 document.pdf"
        self.output_path = self.root / "result 1" / "résultat.md"

    def test_request_round_trip_and_requested_effective_device_distinction(self) -> None:
        request = ConversionRequest(
            job_id="job-研究-1",
            input_path=self.input_path,
            mode="balanced",
            options=ConversionOptions(device="cuda"),
            staging_dir=self.root / "SAMI staging" / "job 1",
            device="cpu",
            attempt=2,
        )

        wire = request.to_wire()
        restored = ConversionRequest.from_json(request.to_json())

        self.assertEqual(wire["input_path"], str(self.input_path))
        self.assertEqual(wire["options"]["device"], "cuda")
        self.assertEqual(wire["device"], "cpu")
        self.assertEqual(restored, request)

    def test_nested_run_result_paths_and_metadata_serialize_explicitly(self) -> None:
        job = JobResult(
            job_id="job-1",
            input_path=self.input_path,
            mode="quality",
            engine="marker",
            device="cpu",
            status="succeeded",
            output_paths=(self.output_path,),
            warnings=({"code": "RECOVERED", "source": self.output_path},),
            duration_seconds=2.5,
            attempts=1,
        )
        run = RunResult(run_id="run-1", results=(job,), exit_code=0)

        encoded = run.to_json()
        decoded_json = json.loads(encoded)
        restored = RunResult.from_json(encoded)

        self.assertEqual(decoded_json["results"][0]["input_path"], str(self.input_path))
        self.assertEqual(decoded_json["results"][0]["output_paths"], [str(self.output_path)])
        self.assertEqual(decoded_json["results"][0]["warnings"][0]["source"], str(self.output_path))
        self.assertEqual(restored.results[0].warnings[0]["source"], str(self.output_path))
        self.assertEqual(restored.results[0].output_paths, run.results[0].output_paths)
        self.assertEqual(restored.results[0].input_path, run.results[0].input_path)
        self.assertEqual(restored.run_id, run.run_id)
        self.assertEqual(restored.totals, {"succeeded": 1, "partial": 0, "failed": 0, "cancelled": 0})

    def test_engine_result_round_trip_keeps_recovered_references_and_paths(self) -> None:
        result = EngineResult(
            markdown="# Résultat\n",
            resources=(Path("figures/图 1.png"),),
            references=(RecoveredReference(page=3, label="référence", destination="https://example.org/研究"),),
            processed_pages=4,
            metrics={"duration": 1.25, "engine": "fast"},
        )
        restored = EngineResult.from_json(result.to_json())
        self.assertEqual(restored, result)
        self.assertEqual(restored.to_wire()["resources"], ["figures/图 1.png"])

    def test_unknown_additive_fields_are_ignored(self) -> None:
        wire = ConversionRequest(
            job_id="job-1", input_path=self.input_path, mode="fast",
            options=ConversionOptions(), staging_dir=Path("/tmp/stage"), device="cpu",
        ).to_wire()
        wire["future_field"] = {"ok": True}
        wire["options"]["future_option"] = "ignored"
        self.assertEqual(ConversionRequest.from_wire(wire).job_id, "job-1")

    def test_invalid_modes_statuses_devices_durations_and_exit_codes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ConversionRequest(
                "", self.input_path, "fast", ConversionOptions(), self.root / "stage", "cpu"
            )
        with self.assertRaises(ValueError):
            ConversionOptions(device="cuda:0")
        with self.assertRaises(ValueError):
            ConversionRequest(
                "job", self.input_path, "draft", ConversionOptions(), self.root / "stage", "cpu"
            )  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            JobResult("job", self.input_path, "fast", "marker", "cpu", "skipped")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            JobResult("job", self.input_path, "fast", "marker", "auto", "succeeded")
        for duration in (-0.01, math.nan, math.inf, -math.inf):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                JobResult("job", self.input_path, "fast", "marker", "cpu", "succeeded", duration_seconds=duration)
        with self.assertRaises(ValueError):
            RunResult("run", (), True)  # type: ignore[arg-type]
        request_values = {
            "job_id": "job", "input_path": self.input_path, "mode": "fast",
            "options": ConversionOptions(), "staging_dir": self.root / "stage", "device": "cpu",
        }
        for attempt in (0, True, 1.5):
            with self.subTest(request_attempt=attempt), self.assertRaises(ValueError):
                ConversionRequest(**request_values, attempt=attempt)  # type: ignore[arg-type]

    def test_invalid_numbers_and_unsupported_metadata_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                JobResult(
                    "job", self.input_path, "fast", "marker", "cpu", "succeeded",
                    warnings=({"metric": value},),
                )
        with self.assertRaises(TypeError):
            JobResult(
                "job", self.input_path, "fast", "marker", "cpu", "succeeded",
                warnings=({"unsupported": object()},),
            )


if __name__ == "__main__":
    unittest.main()
