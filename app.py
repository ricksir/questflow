from __future__ import annotations

"""Composition root do QuestFlow Studio.

A interface responsiva abre exclusivamente no Google Chrome. O núcleo Python e
o banco permanecem em processo separado, comunicando-se pela API local.
"""

from pathlib import Path

from app_shared import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    CONFIG_PATH,
    DATABASE_PATH,
    DEFAULT_CONFIG,
    TAXONOMY_PATH,
    load_config,
)
from desktop_runtime import (
    acquire_single_instance,
    browser_candidates,
    release_single_instance,
    run_chrome,
    show_message,
)


_browser_candidates = browser_candidates  # compatibilidade com diagnóstico antigo


def __getattr__(name: str):
    if name == "QuestFlowApp":
        from app_classic import QuestFlowApp

        return QuestFlowApp
    raise AttributeError(name)


def run_classic() -> None:
    from app_classic import QuestFlowApp

    application = QuestFlowApp()
    application.mainloop()


def main() -> int:
    if not acquire_single_instance():
        show_message("O QuestFlow Studio já está aberto. Feche a outra janela antes de iniciar uma nova instância.")
        return 0

    server = api = None
    try:
        index_path = Path(BASE_DIR, "web", "index.html").resolve()
        if not index_path.exists():
            show_message("A interface web do QuestFlow não foi encontrada.", error=True)
            return 1

        chrome = browser_candidates()
        if not chrome:
            show_message(
                "O Google Chrome não foi encontrado. Instale o Chrome e execute novamente. "
                f"O QuestFlow {APP_VERSION} não abre no Microsoft Edge.",
                error=True,
            )
            return 1

        from web_api import QuestFlowWebApi
        from web_server import QuestFlowLocalServer

        config = load_config()
        api = QuestFlowWebApi(config=config)
        bind_host = "0.0.0.0" if bool(config.get("mobile_lan_enabled", False)) else "127.0.0.1"
        server = QuestFlowLocalServer(api, index_path.parent, bind_host=bind_host)
        server.start()
        api.attach_local_server(server)
        api.set_mobile_server_info({
            "enabled": bind_host != "127.0.0.1",
            "urls": server.mobile_urls(),
            "api_urls": server.mobile_api_urls(),
            "restart_required": False,
        })

        if run_chrome(server, api):
            return 0

        show_message(
            "O Google Chrome foi encontrado, mas a interface não respondeu ao motor local mesmo após as "
            "tentativas automáticas de recuperação. Feche somente as janelas do QuestFlow e tente novamente. "
            "Se persistir, execute INSTALAR_E_DIAGNOSTICAR.bat.",
            error=True,
        )
        return 1
    except Exception as error:
        show_message(f"O QuestFlow não conseguiu iniciar: {error}", error=True)
        return 1
    finally:
        if api is not None:
            try:
                api.shutdown()
            except Exception:
                pass
        if server is not None:
            try:
                server.stop()
            except Exception:
                pass
        release_single_instance()


if __name__ == "__main__":
    raise SystemExit(main())
