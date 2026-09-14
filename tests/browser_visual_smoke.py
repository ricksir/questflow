from __future__ import annotations

import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "artifacts" / "browser-visual-smoke"

VIEWPORTS = (
    ("desktop", 1440, 900),
    ("compact-desktop", 1024, 768),
    ("tablet", 820, 900),
    ("mobile", 390, 844),
)

ROUTES = ("dashboard", "review", "coverage", "flow", "settings")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


def _visible(driver: webdriver.Chrome, selector: str) -> bool:
    return bool(
        driver.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            if (!el) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && rect.width > 0 && rect.height > 0;
            """,
            selector,
        )
    )


def _assert_no_global_overflow(driver: webdriver.Chrome, context: str) -> dict[str, Any]:
    metrics = driver.execute_script(
        """
        const pick = (selector) => {
          const el = document.querySelector(selector);
          if (!el) return null;
          return {
            clientWidth: el.clientWidth,
            scrollWidth: el.scrollWidth,
            overflow: el.scrollWidth - el.clientWidth,
          };
        };
        return {
          innerWidth: window.innerWidth,
          devicePixelRatio: window.devicePixelRatio,
          html: pick('html'),
          body: pick('body'),
          shell: pick('.app-shell'),
          stage: pick('.app-stage'),
          workspace: pick('.workspace'),
        };
        """
    )
    problems = []
    for key in ("html", "body", "shell", "stage", "workspace"):
        item = metrics.get(key)
        if not item:
            continue
        if item["scrollWidth"] > item["clientWidth"] + 2:
            problems.append(
                f"{key}: scrollWidth={item['scrollWidth']} clientWidth={item['clientWidth']}"
            )
    if problems:
        raise AssertionError(f"Overflow horizontal global em {context}: " + "; ".join(problems))
    return metrics


def _activate_route(driver: webdriver.Chrome, route: str) -> None:
    driver.execute_script(
        """
        const button = document.querySelector(`[data-route="${arguments[0]}"]`);
        if (!button) throw new Error(`Rota ausente: ${arguments[0]}`);
        button.click();
        """,
        route,
    )
    WebDriverWait(driver, 12).until(
        lambda d: d.find_element(
            By.CSS_SELECTOR, f'section.page.is-active[data-page="{route}"]'
        )
    )
    time.sleep(0.15)


def _screenshot(driver: webdriver.Chrome, name: str) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.png"
    if not driver.save_screenshot(str(path)):
        raise AssertionError(f"Chrome não conseguiu salvar screenshot: {path}")
    return str(path.relative_to(ROOT))


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"viewports": [], "console": []}

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(QuietHandler, directory=str(WEB_DIR)),
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/index.html"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--force-device-scale-factor=1")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    driver: webdriver.Chrome | None = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(35)

        for label, requested_width, requested_height in VIEWPORTS:
            driver.set_window_size(requested_width, requested_height)
            driver.get(base_url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "appShell"))
            )
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'section.page.is-active[data-page="dashboard"]')
                )
            )
            time.sleep(0.25)

            inner_width = int(driver.execute_script("return window.innerWidth"))
            search_visible = _visible(driver, ".global-search--questions")
            scope_visible = _visible(
                driver, ".global-search--questions .global-search__scope"
            )
            segmented_visible = _visible(driver, ".segmented-control")

            # O hardening responsivo mais recente mantém a busca entre
            # 48rem e 58rem e a oculta apenas abaixo de 48rem.
            expected_search = inner_width > 768
            if search_visible != expected_search:
                raise AssertionError(
                    f"Busca global em {label}: visível={search_visible}, "
                    f"esperado={expected_search}, innerWidth={inner_width}"
                )

            expected_scope = inner_width > 1024 and expected_search
            if scope_visible != expected_scope:
                raise AssertionError(
                    f"Chip de escopo em {label}: visível={scope_visible}, "
                    f"esperado={expected_scope}, innerWidth={inner_width}"
                )

            expected_segmented = inner_width > 640
            if segmented_visible != expected_segmented:
                raise AssertionError(
                    f"Controle de escala em {label}: visível={segmented_visible}, "
                    f"esperado={expected_segmented}, innerWidth={inner_width}"
                )

            viewport_record: dict[str, Any] = {
                "label": label,
                "requested": [requested_width, requested_height],
                "innerWidth": inner_width,
                "searchVisible": search_visible,
                "scopeVisible": scope_visible,
                "segmentedVisible": segmented_visible,
                "routes": {},
            }

            for route in ROUTES:
                _activate_route(driver, route)
                metrics = _assert_no_global_overflow(driver, f"{label}/{route}")
                viewport_record["routes"][route] = metrics

                if route in {"dashboard", "settings"}:
                    viewport_record.setdefault("screenshots", []).append(
                        _screenshot(driver, f"{label}-{route}-light")
                    )

                if route == "settings":
                    grid_columns = driver.execute_script(
                        """
                        const el = document.querySelector('.settings-page .settings-grid');
                        return el ? getComputedStyle(el).gridTemplateColumns : '';
                        """
                    )
                    viewport_record["settingsGridColumns"] = grid_columns
                    column_count = len([part for part in grid_columns.split(" ") if part])
                    expected_columns = 1 if inner_width <= 1024 else 2
                    if column_count != expected_columns:
                        raise AssertionError(
                            f"Grid de Configurações em {label}: {grid_columns!r}; "
                            f"esperado {expected_columns} coluna(s)"
                        )

            driver.execute_script(
                "document.documentElement.setAttribute('data-theme', 'dark')"
            )
            _activate_route(driver, "dashboard")
            _assert_no_global_overflow(driver, f"{label}/dashboard-dark")
            viewport_record.setdefault("screenshots", []).append(
                _screenshot(driver, f"{label}-dashboard-dark")
            )
            driver.execute_script(
                "document.documentElement.setAttribute('data-theme', 'system')"
            )

            report["viewports"].append(viewport_record)

        report["console"] = driver.get_log("browser")
        severe = [
            item
            for item in report["console"]
            if str(item.get("level", "")).upper() == "SEVERE"
            and "favicon" not in str(item.get("message", "")).lower()
        ]
        if severe:
            report["severeConsole"] = severe
            raise AssertionError(
                "Chrome registrou erro(s) SEVERE: "
                + " | ".join(str(item.get("message", ""))[:300] for item in severe[:5])
            )
    finally:
        if driver is not None:
            try:
                report["browserVersion"] = driver.capabilities.get("browserVersion")
                report["chromeDriverVersion"] = (
                    driver.capabilities.get("chrome", {})
                    .get("chromedriverVersion", "")
                    .split(" ")[0]
                )
            except Exception:
                pass
            driver.quit()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        (OUTPUT_DIR / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        "[OK] Browser visual smoke: "
        + ", ".join(
            f"{item['label']}({item['innerWidth']}px)" for item in report["viewports"]
        )
    )


if __name__ == "__main__":
    run()
