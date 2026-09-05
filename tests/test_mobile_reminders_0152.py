import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_0152_uses_local_reminders_without_firebase_token():
    push = read(MOBILE / "src" / "lib" / "push.ts")
    assert "scheduleNotificationAsync" in push
    assert "SchedulableTriggerInputTypes.DAILY" in push
    assert "study-reminders" in push
    assert "getDevicePushTokenAsync" not in push
    assert "getExpoPushTokenAsync" not in push
    assert "registerPushToken" not in push
    assert "googleServicesFile" not in push
    assert "FirebaseApp" not in push


def test_profile_never_exposes_native_notification_exception():
    profile = read(MOBILE / "app" / "(tabs)" / "profile.tsx")
    assert "registerNativePush" in profile
    assert "lembrete local" in profile.lower()
    assert "(e as Error)?.message" not in profile
    assert "Firebase" not in profile
    assert "googleServicesFile" not in profile


def test_pairing_is_qr_first_and_manual_form_is_collapsed():
    pair = read(MOBILE / "app" / "pair.tsx")
    assert "const [showManual, setShowManual] = useState(false)" in pair
    assert "Conecte pelo QR" in pair
    assert "accessibilityState={{ expanded: showManual }}" in pair
    assert "{showManual ? <Card" in pair


def test_release_numbers_identify_the_fixed_build():
    app = json.loads(read(MOBILE / "app.json"))
    package = json.loads(read(MOBILE / "package.json"))
    assert app["expo"]["version"] == "0.16.0"
    assert app["expo"]["android"]["versionCode"] == 22
    assert package["version"] == "0.16.0"
    assert read(ROOT / "VERSION.txt").strip() == "6.24.0"
