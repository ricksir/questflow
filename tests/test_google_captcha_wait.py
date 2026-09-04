from __future__ import annotations

import unittest

from core.google_browser import _wait_for_manual_captcha


class _Body:
    def __init__(self, driver):
        self.driver = driver

    @property
    def text(self):
        return self.driver.body_text


class _FakeClock:
    def __init__(self):
        self.value = 0.0

    def time(self):
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


class _CaptchaDriver:
    def __init__(self, resolve_after_checks: int | None):
        self.resolve_after_checks = resolve_after_checks
        self.checks = 0
        self._current_url = "https://www.google.com/sorry/index"
        self.body_text = "Confirme que você não é um robô"

    @property
    def current_url(self):
        self.checks += 1
        if self.resolve_after_checks is not None and self.checks >= self.resolve_after_checks:
            self._current_url = "https://www.google.com/search?q=Q123"
            self.body_text = "Resultados da pesquisa Q123 banca FGV ano 2024"
        return self._current_url

    def find_element(self, by, value):
        if by == "tag name" and value == "body":
            return _Body(self)
        raise LookupError(value)

    def find_elements(self, by, value):
        if "recaptcha" in str(value).lower() and "/sorry/" in self._current_url:
            return [object()]
        return []


class GoogleCaptchaWaitTests(unittest.TestCase):
    def test_waits_until_user_resolves_captcha(self):
        clock = _FakeClock()
        driver = _CaptchaDriver(resolve_after_checks=4)
        result = _wait_for_manual_captcha(
            driver,
            timeout_seconds=30,
            poll_seconds=1,
            sleep_func=clock.sleep,
            time_func=clock.time,
        )
        self.assertTrue(result["detected"])
        self.assertTrue(result["resolved"])
        self.assertFalse(result["timed_out"])
        self.assertGreaterEqual(result["waited_seconds"], 1)

    def test_keeps_browser_waiting_until_timeout(self):
        clock = _FakeClock()
        driver = _CaptchaDriver(resolve_after_checks=None)
        result = _wait_for_manual_captcha(
            driver,
            timeout_seconds=15,
            poll_seconds=1,
            sleep_func=clock.sleep,
            time_func=clock.time,
        )
        self.assertTrue(result["detected"])
        self.assertFalse(result["resolved"])
        self.assertTrue(result["timed_out"])
        self.assertGreaterEqual(result["waited_seconds"], 15)


if __name__ == "__main__":
    unittest.main()
