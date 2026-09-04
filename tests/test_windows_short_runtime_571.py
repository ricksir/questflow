from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

import installer


ROOT = Path(__file__).resolve().parents[1]


class WindowsShortRuntime571Tests(unittest.TestCase):
    def test_runtime_helper_uses_short_localappdata_root(self) -> None:
        text = (ROOT / "QUESTFLOW_RUNTIME.bat").read_text(encoding="utf-8")
        self.assertIn(r"%LOCALAPPDATA%\QFS", text)
        self.assertIn(r"%QF_RUNTIME_ROOT%\venv", text)
        self.assertNotIn(r"%~dp0.venv", text)

    def test_active_batch_files_do_not_use_project_local_venv(self) -> None:
        files = [
            "INICIAR_QUESTFLOW_STUDIO.bat",
            "INSTALAR_E_DIAGNOSTICAR.bat",
            "REPARAR_INSTALACAO.bat",
            "INICIAR_INTERFACE_CLASSICA.bat",
            "TESTAR_COMPONENTES.bat",
            "TESTAR_SUITE_COMPLETA.bat",
            "VALIDAR_BASE_QUESTFLOW.bat",
            "CONVERTER_QFLOW_ANTIGO.bat",
            "CONFIGURAR_TURSO_CLOUD.bat",
            "VALIDAR_CLOUD_SYNC.bat",
        ]
        for name in files:
            with self.subTest(name=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertNotIn(r".venv\Scripts", text)
                self.assertIn("QUESTFLOW_RUNTIME.bat", text)

    def test_installer_cache_honors_shared_runtime_root(self) -> None:
        with mock.patch.dict(os.environ, {"QF_RUNTIME_ROOT": r"C:\Users\user\AppData\Local\QFS"}, clear=False):
            environment = installer._pip_environment()
            self.assertEqual(
                Path(environment["PIP_CACHE_DIR"]),
                Path(r"C:\Users\user\AppData\Local\QFS") / "pip-cache",
            )

    def test_long_path_failure_gets_specific_diagnostic(self) -> None:
        detail = (
            "ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: "
            r"C:\x\Lib\site-packages\torch\include\ATen\native\transformers\cuda\mem_eff_attention\file.h "
            "HINT: This error might have occurred since this system does not have Windows Long Path Support enabled."
        )
        message = installer._friendly_install_detail(detail)
        self.assertIn("caminho interno muito longo", message)
        self.assertIn("Runtime curto recomendado", message)


if __name__ == "__main__":
    unittest.main()
