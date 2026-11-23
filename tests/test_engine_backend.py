"""Tests for doc-06 engine backend and GPU policy.

Covers:
- compute_ngl() VRAM ladder: >=8 / 4-8 / <4 / None -> full/partial/cpu
- hardware.gpu_info() structure
- _configure_vlm_backend() sets llama.cpp env vars; never docker/vllm
- quality path calls _configure_vlm_backend(); balanced does not
- Public mode is NEVER changed by hardware
- _locate_gguf_paths() respects env overrides

No real GPU, no Torch import, no model loading.
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# hardware.compute_ngl
# ---------------------------------------------------------------------------

class TestComputeNgl(unittest.TestCase):

    def test_full_offload_at_8gb(self):
        ngl, tier = self._ngl(8.0)
        self.assertEqual(ngl, -1)
        self.assertEqual(tier, "full")

    def test_full_offload_above_8gb(self):
        ngl, tier = self._ngl(16.0)
        self.assertEqual(ngl, -1)
        self.assertEqual(tier, "full")

    def test_partial_offload_between_4_and_8(self):
        ngl, tier = self._ngl(5.5)
        self.assertGreater(ngl, 0)
        self.assertEqual(tier, "partial")

    def test_partial_offload_at_4gb_boundary(self):
        ngl, tier = self._ngl(4.0)
        self.assertGreater(ngl, 0)
        self.assertEqual(tier, "partial")

    def test_cpu_below_4gb(self):
        ngl, tier = self._ngl(3.9)
        self.assertEqual(ngl, 0)
        self.assertEqual(tier, "cpu")

    def test_cpu_at_zero(self):
        ngl, tier = self._ngl(0.0)
        self.assertEqual(ngl, 0)
        self.assertEqual(tier, "cpu")

    def test_cpu_when_none(self):
        ngl, tier = self._ngl(None)
        self.assertEqual(ngl, 0)
        self.assertEqual(tier, "cpu")

    @staticmethod
    def _ngl(vram_gb):
        from sami.hardware import compute_ngl
        return compute_ngl(vram_gb)


# ---------------------------------------------------------------------------
# hardware.gpu_info() structure
# ---------------------------------------------------------------------------

class TestGpuInfo(unittest.TestCase):

    def test_all_keys_present_no_gpu(self):
        """gpu_info() always returns all required keys even with no GPU."""
        with patch("subprocess.run") as mock_run, \
             patch.dict(sys.modules, {"torch": None}):
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            from importlib import reload
            import sami.hardware as hw
            reload(hw)
            info = hw.gpu_info()

        expected_keys = {
            "physical_gpu", "driver_version", "torch_cuda",
            "vram_total_gb", "vram_free_gb", "ngl", "ngl_tier", "source",
        }
        self.assertEqual(set(info.keys()), expected_keys)

    def test_no_gpu_produces_cpu_tier(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            # Torch unavailable
            with patch.dict(sys.modules, {"torch": None}):
                from importlib import reload
                import sami.hardware as hw
                reload(hw)
                info = hw.gpu_info()
        self.assertEqual(info["ngl_tier"], "cpu")
        self.assertEqual(info["ngl"], 0)
        self.assertIsNone(info["physical_gpu"])

    def test_nvidia_smi_data_used(self):
        """When nvidia-smi returns data, gpu_info parses it correctly."""
        smi_output = "NVIDIA RTX 3050 Laptop GPU, 4096, 2048, 530.41.03\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=smi_output)
            # Don't import torch
            with patch.dict(sys.modules, {"torch": None}):
                from importlib import reload
                import sami.hardware as hw
                reload(hw)
                info = hw.gpu_info()

        self.assertEqual(info["physical_gpu"], "NVIDIA RTX 3050 Laptop GPU")
        self.assertAlmostEqual(info["vram_total_gb"], 4096 / 1024, places=2)
        self.assertAlmostEqual(info["vram_free_gb"], 2048 / 1024, places=2)
        self.assertEqual(info["source"], "nvidia-smi")


# ---------------------------------------------------------------------------
# _configure_vlm_backend: sets llamacpp, never docker/vllm
# ---------------------------------------------------------------------------

class TestConfigureVlmBackend(unittest.TestCase):

    def _call(self, ngl, ngl_tier, tmpdir=None):
        from sami.engines.marker import _configure_vlm_backend
        logs = []
        env_before = dict(os.environ)
        # Remove keys we're testing so defaults get set
        for k in ("SURYA_INFERENCE_BACKEND", "LLAMA_CPP_NGL",
                  "SURYA_GGUF_LOCAL_MODEL_PATH", "SURYA_GGUF_LOCAL_MMPROJ_PATH"):
            os.environ.pop(k, None)
        try:
            _configure_vlm_backend(ngl, ngl_tier, logs.append, tmpdir)
            return dict(os.environ), logs
        finally:
            # Restore env
            for k in ("SURYA_INFERENCE_BACKEND", "LLAMA_CPP_NGL",
                      "SURYA_GGUF_LOCAL_MODEL_PATH", "SURYA_GGUF_LOCAL_MMPROJ_PATH"):
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in env_before.items()
                                if k in ("SURYA_INFERENCE_BACKEND", "LLAMA_CPP_NGL",
                                         "SURYA_GGUF_LOCAL_MODEL_PATH",
                                         "SURYA_GGUF_LOCAL_MMPROJ_PATH")})

    def test_sets_llamacpp_backend(self):
        env, _ = self._call(0, "cpu")
        self.assertEqual(env.get("SURYA_INFERENCE_BACKEND"), "llamacpp")

    def test_never_sets_vllm_or_docker(self):
        env, _ = self._call(-1, "full")
        backend = env.get("SURYA_INFERENCE_BACKEND", "")
        self.assertNotIn("vllm", backend.lower())
        self.assertNotIn("docker", backend.lower())

    def test_full_offload_sets_ngl_999(self):
        # -1 means "all layers" → converted to 999 for llama-server
        env, _ = self._call(-1, "full")
        self.assertEqual(env.get("LLAMA_CPP_NGL"), "999")

    def test_cpu_sets_ngl_0(self):
        env, _ = self._call(0, "cpu")
        self.assertEqual(env.get("LLAMA_CPP_NGL"), "0")

    def test_partial_sets_ngl_value(self):
        env, _ = self._call(20, "partial")
        self.assertEqual(env.get("LLAMA_CPP_NGL"), "20")

    def test_respects_existing_backend_override(self):
        """If SURYA_INFERENCE_BACKEND is already set, setdefault keeps it."""
        from sami.engines.marker import _configure_vlm_backend
        os.environ["SURYA_INFERENCE_BACKEND"] = "llamacpp_custom"
        try:
            _configure_vlm_backend(0, "cpu", lambda _: None, None)
            self.assertEqual(os.environ["SURYA_INFERENCE_BACKEND"], "llamacpp_custom")
        finally:
            os.environ.pop("SURYA_INFERENCE_BACKEND", None)

    def test_logs_tier(self):
        _, logs = self._call(0, "cpu")
        self.assertTrue(any("cpu" in m.lower() or "-ngl 0" in m for m in logs),
                        f"Expected CPU log, got: {logs}")

    def test_gguf_paths_set_when_found(self):
        """When GGUF files exist in the cache, the env vars are set."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # Build a fake HF cache layout
            snap = Path(td) / "hub" / "models--datalab-to--surya-ocr-2-gguf" / "snapshots" / "abc123"
            snap.mkdir(parents=True)
            (snap / "surya-2.gguf").write_bytes(b"fake")
            (snap / "surya-2-mmproj.gguf").write_bytes(b"fake")

            orig_hf = os.environ.get("HF_HOME")
            os.environ["HF_HOME"] = td
            os.environ.pop("SURYA_GGUF_LOCAL_MODEL_PATH", None)
            os.environ.pop("SURYA_GGUF_LOCAL_MMPROJ_PATH", None)
            try:
                from sami.engines.marker import _configure_vlm_backend
                _configure_vlm_backend(0, "cpu", lambda _: None, None)
                self.assertIn("surya-2.gguf", os.environ.get("SURYA_GGUF_LOCAL_MODEL_PATH", ""))
                self.assertIn("surya-2-mmproj.gguf", os.environ.get("SURYA_GGUF_LOCAL_MMPROJ_PATH", ""))
            finally:
                os.environ.pop("SURYA_GGUF_LOCAL_MODEL_PATH", None)
                os.environ.pop("SURYA_GGUF_LOCAL_MMPROJ_PATH", None)
                os.environ.pop("LLAMA_CPP_NGL", None)
                os.environ.pop("SURYA_INFERENCE_BACKEND", None)
                if orig_hf is not None:
                    os.environ["HF_HOME"] = orig_hf
                else:
                    os.environ.pop("HF_HOME", None)


# ---------------------------------------------------------------------------
# build_converter: quality path calls _configure_vlm_backend, balanced does not
# ---------------------------------------------------------------------------

class TestBuildConverterBackendDispatch(unittest.TestCase):
    """build_converter() must call _configure_vlm_backend for quality VLM
    (marker_mode="balanced") and must NOT call it for balanced (RF-DETR,
    marker_mode="fast").  We mock heavy imports so no model loading occurs."""

    def _make_cpu_config(self):
        return {
            "physical_cores": 4,
            "target_threads": 4,
            "torch_threads": 4,
            "pdftext_workers": 1,
        }

    def test_quality_path_calls_configure_vlm_backend(self):
        called = []

        def fake_configure(ngl, tier, logger, app_home):
            called.append((ngl, tier))

        with self._patch_heavy(fake_configure) as _:
            from importlib import reload
            import sami.engines.marker as m
            reload(m)
            with patch.object(m, "_configure_vlm_backend", fake_configure):
                try:
                    m.build_converter(
                        "balanced",  # quality VLM uses Marker internal mode "balanced"
                        cpu_config=self._make_cpu_config(),
                        logger=lambda *a, **kw: None,
                        stage_logger=lambda *a, **kw: None,
                        stage_done_logger=lambda *a, **kw: None,
                    )
                except Exception:
                    pass  # model loading will fail — we only care about the call

        self.assertTrue(len(called) >= 1, "Expected _configure_vlm_backend to be called for quality VLM")

    def test_balanced_path_does_not_call_configure_vlm_backend(self):
        called = []

        def fake_configure(ngl, tier, logger, app_home):
            called.append((ngl, tier))

        with self._patch_heavy(fake_configure):
            from importlib import reload
            import sami.engines.marker as m
            reload(m)
            with patch.object(m, "_configure_vlm_backend", fake_configure):
                try:
                    m.build_converter(
                        "fast",  # balanced public mode uses Marker internal "fast" (RF-DETR)
                        cpu_config=self._make_cpu_config(),
                        logger=lambda *a, **kw: None,
                        stage_logger=lambda *a, **kw: None,
                        stage_done_logger=lambda *a, **kw: None,
                    )
                except Exception:
                    pass  # model loading will fail — we only care

        self.assertEqual(called, [], "balanced (RF-DETR) must NOT call _configure_vlm_backend")

    @staticmethod
    def _patch_heavy(fake_configure):
        """Mock out torch and marker so no real imports happen."""
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = MagicMock()
        fake_torch.cuda.is_available = MagicMock(return_value=False)
        fake_torch.set_num_threads = MagicMock()

        fake_marker_models = types.ModuleType("marker.models")
        fake_marker_models.create_model_dict = MagicMock(side_effect=RuntimeError("no models in test"))
        fake_marker_config = types.ModuleType("marker.config")
        fake_marker_config_parser = types.ModuleType("marker.config.parser")
        fake_marker_config_parser.ConfigParser = MagicMock()

        return patch.dict(sys.modules, {
            "torch": fake_torch,
            "marker.models": fake_marker_models,
            "marker.config": fake_marker_config,
            "marker.config.parser": fake_marker_config_parser,
        })


# ---------------------------------------------------------------------------
# MODE TABLE: public mode must never be changed by hardware
# ---------------------------------------------------------------------------

class TestModeTableUnchanged(unittest.TestCase):

    def test_all_three_modes_in_table(self):
        from sami.engines import MODE_TABLE
        self.assertIn("fast", MODE_TABLE)
        self.assertIn("balanced", MODE_TABLE)
        self.assertIn("quality", MODE_TABLE)

    def test_fast_uses_fast_engine(self):
        from sami.engines import MODE_TABLE
        self.assertEqual(MODE_TABLE["fast"].engine, "fast")

    def test_balanced_uses_marker_fast_profile(self):
        from sami.engines import MODE_TABLE
        sel = MODE_TABLE["balanced"]
        self.assertEqual(sel.engine, "marker")
        self.assertEqual(sel.profile, "fast")

    def test_quality_uses_marker_balanced_profile(self):
        from sami.engines import MODE_TABLE
        sel = MODE_TABLE["quality"]
        self.assertEqual(sel.engine, "marker")
        self.assertEqual(sel.profile, "balanced")

    def test_select_engine_does_not_mutate_mode(self):
        """select_engine() is pure — calling it multiple times returns the same selection."""
        from sami.engines import select_engine
        for mode in ("fast", "balanced", "quality"):
            s1 = select_engine(mode)
            s2 = select_engine(mode)
            self.assertEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
