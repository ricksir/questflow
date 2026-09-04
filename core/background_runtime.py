from __future__ import annotations

"""Runtime assíncrono isolado e supervisionável para tarefas de I/O.

O QuestFlow mantém um único event loop de background para operações que se
beneficiam de concorrência assíncrona. Trabalho CPU/OCR continua no pool
tradicional para evitar misturar cargas incompatíveis.
"""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import threading
import time
import inspect
from typing import Awaitable, Callable, TypeVar, Any


T = TypeVar("T")


class BackgroundRuntime:
    def __init__(self, *, max_concurrency: int = 4):
        self._max_concurrency = max(1, int(max_concurrency))
        self._state_lock = threading.RLock()
        self._closed = False
        self._generation = 0
        self._submitted = 0
        self._completed = 0
        self._failed = 0
        self._active = 0
        self._last_heartbeat = 0.0
        self._last_error = ""
        self._build_runtime()

    def _build_runtime(self) -> None:
        self._generation += 1
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="questflow-async-runtime")
        self._ready = threading.Event()
        self._semaphore: asyncio.Semaphore | None = None
        self._io_executor = ThreadPoolExecutor(
            max_workers=self._max_concurrency,
            thread_name_prefix="questflow-async-io",
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("O runtime assíncrono do QuestFlow não iniciou.")

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.set_default_executor(self._io_executor)
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._last_heartbeat = time.monotonic()
        self._ready.set()
        heartbeat = self._loop.create_task(self._heartbeat_loop(), name="questflow-async-heartbeat")
        try:
            self._loop.run_forever()
        finally:
            heartbeat.cancel()
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            self._io_executor.shutdown(wait=False, cancel_futures=True)

    async def _heartbeat_loop(self) -> None:
        while True:
            self._last_heartbeat = time.monotonic()
            await asyncio.sleep(1.0)

    async def _bounded(self, awaitable: Awaitable[T]) -> T:
        assert self._semaphore is not None
        started_inner = False
        try:
            async with self._semaphore:
                with self._state_lock:
                    self._active += 1
                try:
                    started_inner = True
                    result = await awaitable
                    with self._state_lock:
                        self._completed += 1
                    return result
                except BaseException as error:
                    with self._state_lock:
                        self._failed += 1
                        self._last_error = str(error)[:1000]
                    raise
                finally:
                    with self._state_lock:
                        self._active = max(0, self._active - 1)
        finally:
            # Se a tarefa for cancelada enquanto ainda aguarda vaga no
            # semáforo (por exemplo, durante shutdown/restart), o coroutine
            # interno nunca chegou a ser aguardado. Fechá-lo explicitamente
            # evita vazamentos e RuntimeWarning sem executar trabalho fora do
            # ciclo de vida supervisionado.
            if not started_inner and inspect.iscoroutine(awaitable):
                awaitable.close()

    def submit(self, awaitable: Awaitable[T]) -> Future[T]:
        if self._closed:
            raise RuntimeError("Runtime já encerrado.")
        if not self._thread.is_alive():
            raise RuntimeError("Runtime assíncrono indisponível.")
        with self._state_lock:
            self._submitted += 1
        return asyncio.run_coroutine_threadsafe(self._bounded(awaitable), self._loop)

    async def _run_blocking_bounded(self, func: Callable[..., T], args: tuple, kwargs: dict) -> T:
        assert self._semaphore is not None
        async with self._semaphore:
            with self._state_lock:
                self._active += 1
            try:
                result = await asyncio.to_thread(func, *args, **kwargs)
                with self._state_lock:
                    self._completed += 1
                return result
            except BaseException as error:
                with self._state_lock:
                    self._failed += 1
                    self._last_error = str(error)[:1000]
                raise
            finally:
                with self._state_lock:
                    self._active = max(0, self._active - 1)

    def run_blocking(self, func: Callable[..., T], /, *args, **kwargs) -> Future[T]:
        """Agenda uma função bloqueante sem criar coroutine fora do event loop.

        A criação do coroutine ocorre somente dentro da thread do loop. Isso
        torna shutdown/restart idempotentes mesmo quando uma tarefa foi
        solicitada e o aplicativo fecha imediatamente depois, evitando
        ``coroutine was never awaited``.
        """
        if self._closed:
            raise RuntimeError("Runtime já encerrado.")
        if not self._thread.is_alive():
            raise RuntimeError("Runtime assíncrono indisponível.")

        result_future: Future[T] = Future()
        with self._state_lock:
            self._submitted += 1

        def schedule() -> None:
            if result_future.cancelled():
                return
            if self._closed or not self._loop.is_running():
                if not result_future.done():
                    result_future.set_exception(RuntimeError("Runtime assíncrono indisponível."))
                return
            task = self._loop.create_task(
                self._run_blocking_bounded(func, args, kwargs),
                name="questflow-async-blocking",
            )

            def transfer(done: asyncio.Task) -> None:
                if result_future.cancelled() or result_future.done():
                    return
                try:
                    result_future.set_result(done.result())
                except BaseException as error:
                    result_future.set_exception(error)

            task.add_done_callback(transfer)

        try:
            self._loop.call_soon_threadsafe(schedule)
        except Exception as error:
            if not result_future.done():
                result_future.set_exception(error)
        return result_future

    def health(self) -> dict[str, Any]:
        age = max(0.0, time.monotonic() - self._last_heartbeat) if self._last_heartbeat else 9999.0
        alive = bool(self._thread and self._thread.is_alive())
        ok = alive and age < 5.0 and not self._closed
        with self._state_lock:
            return {
                "ok": ok,
                "state": "healthy" if ok else ("disabled" if self._closed else "degraded"),
                "thread_alive": alive,
                "loop_running": bool(getattr(self, "_loop", None) and self._loop.is_running()),
                "heartbeat_age_seconds": round(age, 3),
                "max_concurrency": self._max_concurrency,
                "active": self._active,
                "submitted": self._submitted,
                "completed": self._completed,
                "failed": self._failed,
                "generation": self._generation,
                "last_error": self._last_error,
            }

    def reconfigure(self, *, max_concurrency: int) -> dict[str, Any]:
        target = max(1, int(max_concurrency))
        if target == self._max_concurrency:
            return {"ok": True, "changed": False, "health": self.health()}
        self._max_concurrency = target
        result = self.restart()
        return {"ok": bool(result.get("ok")), "changed": True, "health": self.health()}

    def restart(self) -> dict[str, Any]:
        if self._closed:
            return {"ok": False, "error": "Runtime já encerrado definitivamente."}
        old_thread = self._thread
        try:
            if old_thread and old_thread.is_alive():
                self._loop.call_soon_threadsafe(self._loop.stop)
                old_thread.join(timeout=2.0)
        except Exception:
            pass
        self._build_runtime()
        return {"ok": True, "health": self.health()}

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        self._thread.join(timeout=max(0.1, float(timeout)))


__all__ = ["BackgroundRuntime"]
