export const MOBILE_APP_VERSION = '0.16.0';
export const MOBILE_SCHEMA_VERSION = 1;
export const MOBILE_CONTRACT = 'questflow.mobile.v1';

// Conservative timing rule: foreground is not enough to prove active study.
// After this interval without touch/selection/scroll/app-state activity, time
// stops accumulating until the user interacts again.
export const ACTIVE_IDLE_CUTOFF_MS = 60_000;
export const ACTIVE_TICK_MAX_MS = 2_500;
export const NETWORK_TIMEOUT_MS = 12_000;
export const OUTBOX_BATCH_SIZE = 100;
