from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ManagerV2Hotfix6100Tests(unittest.TestCase):
    def test_external_updater_is_used(self):
        manager = (ROOT / 'questflow_manager.ps1').read_text(encoding='utf-8')
        self.assertIn('questflow_external_updater.ps1', manager)
        self.assertIn("Start-Process -FilePath 'powershell.exe'", manager)
        self.assertIn("-PassThru -Wait", manager)

    def test_external_updater_has_visible_progress_and_logs(self):
        updater = (ROOT / 'questflow_external_updater.ps1').read_text(encoding='utf-8')
        self.assertIn('ATUALIZADOR EXTERNO (MANAGER V2.7)', updater)
        self.assertIn('Atualizacao em andamento...', updater)
        self.assertIn("Join-Path $RuntimeRoot 'logs'", updater)
        self.assertIn('NAO feche esta janela', updater)


    def test_python_launcher_is_materialized_as_array(self):
        updater = (ROOT / 'questflow_external_updater.ps1').read_text(encoding='utf-8')
        self.assertIn('$python = @(Find-Python)', updater)
        self.assertIn('$exe = [string]$python[0]', updater)
        self.assertIn('Python selecionado:', updater)
        self.assertIn('Executavel Python nao encontrado:', updater)


    def test_zip_preflight_rejects_windows_absolute_paths(self):
        updater = (ROOT / 'questflow_external_updater.ps1').read_text(encoding='utf-8')
        self.assertIn('Assert-SafeZipEntries', updater)
        self.assertIn("-match '^[A-Za-z]:'", updater)
        hardening = (ROOT / 'core' / 'production_hardening.py').read_text(encoding='utf-8')
        self.assertIn('PurePosixPath', hardening)
        self.assertIn('ZIP contém caminho inseguro', hardening)

    def test_repair_only_copies_manager_files(self):
        repair = (ROOT / 'REPARAR_QUESTFLOW_MANAGER.bat').read_text(encoding='utf-8')
        self.assertIn('QUESTFLOW.bat', repair)
        self.assertIn('questflow_manager.ps1', repair)
        self.assertIn('questflow_external_updater.ps1', repair)
        self.assertNotIn('xcopy "%~dp0data', repair.lower())
        self.assertNotIn('robocopy "%~dp0data', repair.lower())

    def test_launcher_keeps_error_visible(self):
        launcher = (ROOT / 'QUESTFLOW.bat').read_text(encoding='utf-8')
        self.assertIn('if not "%QF_RC%"=="0"', launcher)
        self.assertIn('pause', launcher.lower())

if __name__ == '__main__':
    unittest.main()
