from __future__ import annotations

import asyncio
import time
import unittest

from core.background_runtime import BackgroundRuntime


class BackgroundRuntimeTests(unittest.TestCase):
    def test_runs_blocking_work(self) -> None:
        runtime = BackgroundRuntime(max_concurrency=2)
        try:
            result = runtime.run_blocking(lambda value: value * 2, 21).result(timeout=3)
            self.assertEqual(result, 42)
        finally:
            runtime.shutdown()

    def test_runs_coroutine(self) -> None:
        runtime = BackgroundRuntime(max_concurrency=2)
        try:
            async def work() -> int:
                await asyncio.sleep(0.01)
                return 7
            self.assertEqual(runtime.submit(work()).result(timeout=3), 7)
        finally:
            runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
