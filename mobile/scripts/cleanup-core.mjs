import fs from 'node:fs';
fs.rmSync(new URL('../.core-test-build', import.meta.url), { recursive: true, force: true });
