"""Tests for GPU policy and Marker backend configuration."""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


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
            "vram_total_gb", "vram_free_gb", "source",
        }
        self.assertEqual(set(info.keys()), expected_keys)

    def test_no_gpu_leaves_vram_unknown(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            # Torch unavailable
            with patch.dict(sys.modules, {"torch": None}):
                from importlib import reload
                import sami.hardware as hw
                reload(hw)
                info = hw.gpu_info()
        self.assertIsNone(info["vram_free_gb"])
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

    def _call(self, *, cuda=False, fit=True, **overrides):
        from sami.engines.marker import _configure_vlm_backend

        logs = []
        with (
            patch.dict(os.environ, overrides, clear=True),
            patch("sami.llama_runtime.ensure_server", return_value=(Path("llama-server"), cuda)) as ensure,
            patch("sami.llama_runtime.supports_vram_fit", return_value=fit),
        ):
            use_cuda = _configure_vlm_backend(logs.append, Path("."))
            return dict(os.environ), logs, use_cuda, ensure

    def test_uses_cpu_without_a_cuda_runtime(self):
        env, logs, use_cuda, _ = self._call()
        self.assertFalse(use_cuda)
        self.assertEqual(env["SURYA_INFERENCE_BACKEND"], "llamacpp")
        self.assertEqual(env["LLAMA_CPP_NGL"], "0")
        self.assertEqual(env["LLAMA_CPP_EXTRA_ARGS"], "--device none")
        self.assertIn("CPU", logs[-1])

    def test_cuda_runtime_fits_layers_when_loading_the_model(self):
        env, logs, use_cuda, ensure = self._call(cuda=True)
        self.assertTrue(use_cuda)
        self.assertTrue(ensure.call_args.kwargs["want_cuda"])
        self.assertEqual(env["LLAMA_CPP_NGL"], "0")
        self.assertEqual(env["LLAMA_CPP_EXTRA_ARGS"], "--n-gpu-layers auto --fit on")
        self.assertNotIn("SURYA_INFERENCE_PARALLEL", env)
        self.assertIn("automatic layer fitting", logs[-1])

    def test_cuda_runtime_without_fitting_support_uses_cpu(self):
        env, logs, use_cuda, _ = self._call(cuda=True, fit=False)
        self.assertFalse(use_cuda)
        self.assertEqual(env["LLAMA_CPP_EXTRA_ARGS"], "--device none")
        self.assertIn("lacks automatic VRAM fitting", logs[0])

    def test_manual_layer_count_works_without_fitting_support(self):
        env, _, use_cuda, _ = self._call(cuda=True, fit=False, LLAMA_CPP_NGL="20")
        self.assertTrue(use_cuda)
        self.assertEqual(env["LLAMA_CPP_NGL"], "20")
        self.assertNotIn("LLAMA_CPP_EXTRA_ARGS", env)
        self.assertEqual(self._call(cuda=True, LLAMA_CPP_NGL="-1")[0]["LLAMA_CPP_NGL"], "999")

    def test_explicit_cpu_disables_automatic_fitting(self):
        for override in ({"LLAMA_CPP_NGL": "0"}, {"TORCH_DEVICE": "cpu"}):
            with self.subTest(override=override):
                env, _, use_cuda, ensure = self._call(**override)
                self.assertFalse(use_cuda)
                self.assertFalse(ensure.call_args.kwargs["want_cuda"])
                self.assertEqual(env["LLAMA_CPP_NGL"], "0")

    def test_respects_existing_backend_override(self):
        env, _, _, ensure = self._call(SURYA_INFERENCE_BACKEND="vllm")
        self.assertEqual(env["SURYA_INFERENCE_BACKEND"], "vllm")
        self.assertNotIn("LLAMA_CPP_NGL", env)
        ensure.assert_not_called()

    def test_gguf_paths_set_when_found(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as td:
            snapshots = Path(td) / "hub" / "models--datalab-to--surya-ocr-2-gguf" / "snapshots" / "abc123"
            snapshots.mkdir(parents=True)
            (snapshots / "surya-2.gguf").touch()
            (snapshots / "surya-2-mmproj.gguf").touch()
            env, _, _, _ = self._call(HF_HOME=td)
            self.assertEqual(env["SURYA_GGUF_LOCAL_MODEL_PATH"], str(snapshots / "surya-2.gguf"))
            self.assertEqual(env["SURYA_GGUF_LOCAL_MMPROJ_PATH"], str(snapshots / "surya-2-mmproj.gguf"))


class TestBuildConverterBackendDispatch(unittest.TestCase):
    def test_both_marker_profiles_pass_llamacpp_explicitly(self):
        from sami.engines.marker import build_converter

        def create_model_dict(*, inference_backend):
            self.assertEqual(inference_backend, "llamacpp")
            self.assertEqual(os.environ["LLAMA_CPP_EXTRA_ARGS"], "--n-gpu-layers auto --fit on")
            raise RuntimeError("stop before model startup")

        with patch.dict(sys.modules, {
            "torch": types.SimpleNamespace(set_num_threads=MagicMock()),
            "marker.models": types.SimpleNamespace(create_model_dict=create_model_dict),
            "marker.config.parser": types.SimpleNamespace(ConfigParser=MagicMock()),
            "surya.settings": types.SimpleNamespace(settings=types.SimpleNamespace()),
        }), patch("sami.hardware.gpu_info"), patch("sami.hardware.describe_gpu"), patch(
            "sami.llama_runtime.ensure_server", return_value=(Path("llama-server"), True),
        ), patch("sami.llama_runtime.supports_vram_fit", return_value=True):
            for profile in ("fast", "balanced"):
                with self.subTest(profile=profile), patch.dict(os.environ, {}, clear=True):
                    with self.assertRaisesRegex(RuntimeError, "stop before model startup"):
                        build_converter(
                            profile, cpu_config={
                                "torch_threads": 1, "pdftext_workers": 1,
                                "physical_cores": 1, "target_threads": 1,
                            },
                            logger=lambda _: None, stage_logger=None, stage_done_logger=None,
                            app_home=Path("."),
                        )


class TestLlamaRuntime(unittest.TestCase):
    def test_picks_newest_compatible_pair(self):
        from sami.llama_runtime import _select_assets

        def asset(version, runtime=False):
            prefix = "cudart-" if runtime else ""
            return {"name": f"{prefix}llama-b123-bin-ubuntu-cuda-{version}-x64.tar.gz"}

        older = (asset("12.8"), asset("12.8", runtime=True))
        assets = [*older, asset("13.3"), asset("13.5"), asset("13.5", runtime=True)]
        kwargs = {"platform_id": "ubuntu", "arch": "x64", "extension": ".tar.gz"}
        self.assertEqual(_select_assets(assets, driver_version=(13, 3), **kwargs), older)
        self.assertEqual(_select_assets(assets, driver_version=(13, 5), **kwargs), tuple(assets[-2:]))


class TestSuryaCleanup(unittest.TestCase):
    def test_only_terminates_servers_started_by_this_run(self):
        from sami.processes import _stop_surya_children

        owned = MagicMock()
        owned.cmdline.return_value = ["python", "-m", "surya.fast_layout.server"]
        existing = MagicMock()
        existing.cmdline.return_value = ["python", "-m", "surya.ocr_error.server"]
        unrelated = MagicMock()
        unrelated.name.return_value = "python"
        unrelated.cmdline.return_value = ["python", "script.py"]
        llama = MagicMock()
        llama.name.return_value = "llama-server"
        llama.cmdline.return_value = ["llama-server", "--port", "12345"]
        with (
            patch("psutil.Process") as process,
            patch("psutil.wait_procs", return_value=([], [])),
        ):
            process.return_value.children.return_value = [owned, existing, unrelated, llama]
            _stop_surya_children("llama-server", {existing})
        owned.terminate.assert_called_once()
        llama.terminate.assert_called_once()
        existing.terminate.assert_not_called()
        unrelated.terminate.assert_not_called()


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
