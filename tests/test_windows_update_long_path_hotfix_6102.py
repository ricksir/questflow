from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from core.production_hardening import extract_update_zip


ROOT = Path(__file__).resolve().parents[1]


class WindowsUpdateLongPathHotfix6102Tests(unittest.TestCase):
    def test_extract_update_zip_skips_mobile_dependency_tree_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            package = base / 'QuestFlow_Studio_6.10.2_Mobile_0.7.3_UPDATE.zip'
            with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('QuestFlow/VERSION.txt', '6.10.2\n')
                zf.writestr('QuestFlow/app_shared.py', 'APP_VERSION = "6.10.2"\n')
                zf.writestr('QuestFlow/mobile/src/app.tsx', '// source\n')
                zf.writestr(
                    'QuestFlow/mobile/node_modules/expo-camera/prebuilds/spm-deps/ZXingObjC/release/'
                    'ZXingObjC.xcframework/ios-arm64_x86_64-simulator/dSYMs/ZXingObjC.framework.dSYM/'
                    'Contents/Resources/Relocations/aarch64/ZXingObjC.yml',
                    'transient',
                )
                zf.writestr('QuestFlow/mobile/.expo/settings.json', '{}')
                zf.writestr('QuestFlow/data/questflow_questions.sqlite', 'must-not-extract')

            staged = extract_update_zip(package, base / 'stage')
            self.assertEqual(staged.name, 'QuestFlow')
            self.assertTrue((staged / 'VERSION.txt').exists())
            self.assertTrue((staged / 'mobile' / 'src' / 'app.tsx').exists())
            self.assertFalse((staged / 'mobile' / 'node_modules').exists())
            self.assertFalse((staged / 'mobile' / '.expo').exists())
            self.assertFalse((staged / 'data').exists())

    def test_external_updater_prefers_current_install_runner(self) -> None:
        updater = (ROOT / 'questflow_external_updater.ps1').read_text(encoding='utf-8')
        install_runner = "$runner = Join-Path $InstallRoot 'questflow_update_runner.py'"
        runtime_runner = "$fallbackRunner = Join-Path $RuntimeRoot 'updater\\questflow_update_runner.py'"
        self.assertIn(install_runner, updater)
        self.assertIn(runtime_runner, updater)
        self.assertLess(updater.index(install_runner), updater.index(runtime_runner))

    def test_current_release_is_6103(self) -> None:
        self.assertEqual((ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip(), '6.24.0')
        self.assertIn('version = "6.24.0"', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
