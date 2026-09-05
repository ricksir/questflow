import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_qr_scan_exchanges_the_token_immediately_and_only_once():
    pair = read(MOBILE / "app" / "pair.tsx")
    assert "handleBarcodeScanned" in pair
    assert "scanConsumed.current" in pair
    assert "connectPayload(parsed.server, parsed.token, parsed.servers, parsed.cloud)" in pair
    assert "onBarcodeScanned={handleBarcodeScanned}" in pair
    assert "router.replace('/(tabs)/today')" in pair


def test_pairing_exposes_safe_loading_and_recovery_messages():
    pair = read(MOBILE / "app" / "pair.tsx")
    assert "QR lido — conectando" in pair
    assert "mesma rede Wi-Fi" in pair
    assert "Firewall do Windows" in pair
    assert "expirou ou já foi usado" in pair
    assert "invalid token" in pair


def test_studio_uses_the_current_mobile_release_in_pairing_feedback():
    app = read(ROOT / "web" / "app.js")
    enhancement = read(ROOT / "web" / "questflow621.js")
    assert "currentMobileRelease" in app
    assert "QuestFlow Mobile 0.14.0" not in app
    assert "build 0.14" not in enhancement


def test_release_numbers_identify_the_fixed_build():
    app = json.loads(read(MOBILE / "app.json"))
    package = json.loads(read(MOBILE / "package.json"))
    assert app["expo"]["version"] == "0.16.0"
    assert app["expo"]["android"]["versionCode"] == 22
    assert package["version"] == "0.16.0"
    assert read(ROOT / "VERSION.txt").strip() == "6.24.0"
