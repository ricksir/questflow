import unittest
from pathlib import Path


class RuntimeOrphanRecovery541Tests(unittest.TestCase):
    def test_runtime_uses_heartbeat_as_authoritative_signal(self):
        source = Path(__file__).resolve().parents[1].joinpath('desktop_runtime.py').read_text(encoding='utf-8')
        self.assertIn('heartbeat_timeout = HEARTBEAT_TIMEOUT_SECONDS', source)
        self.assertIn('heartbeat_grace = HEARTBEAT_CLOSE_GRACE_SECONDS', source)
        self.assertIn('suspend_gap_threshold = SUSPEND_GAP_THRESHOLD_SECONDS', source)
        self.assertIn('resume_recovery = True', source)
        self.assertIn('"interface_relaunch_started"', source)
        self.assertNotIn('while process.poll() is None or server.last_heartbeat_age <= 20.0', source)
        self.assertIn('if server.last_heartbeat_age <= heartbeat_timeout', source)

    def test_recovery_utility_exists(self):
        root = Path(__file__).resolve().parents[1]
        recovery = root / 'RECUPERAR_QUESTFLOW.bat'
        self.assertTrue(recovery.exists())
        text = recovery.read_text(encoding='utf-8', errors='replace')
        self.assertIn('Get-CimInstance Win32_Process', text)
        self.assertIn('pythonw.exe', text)

    def test_turso_instructions_do_not_require_tursodb(self):
        root = Path(__file__).resolve().parents[1]
        for rel in ['turso_setup.py','INSTALAR_TURSO_CLI_WSL.bat','docs/CLOUD_SYNC_TURSO_5.4.0.md']:
            text=(root/rel).read_text(encoding='utf-8',errors='replace')
            self.assertNotIn('turso db create questflow --tursodb', text)
            self.assertIn('turso db create questflow', text)

if __name__ == '__main__':
    unittest.main()
