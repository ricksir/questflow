import * as SQLite from 'expo-sqlite';
import type { Feedback, LearningEvent, MobileQuestion, OfflineStudyPack, OutboxRow } from './types';

let databasePromise: Promise<SQLite.SQLiteDatabase> | null = null;

export async function getDb(): Promise<SQLite.SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = SQLite.openDatabaseAsync('questflow-mobile.db').then(async (db) => {
      await db.execAsync(`
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS qf_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS qf_outbox (
          event_id TEXT PRIMARY KEY,
          event_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS qf_question_cache (
          question_id TEXT NOT NULL,
          revision INTEGER NOT NULL,
          payload_json TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY(question_id, revision)
        );
        CREATE TABLE IF NOT EXISTS qf_local_attempts (
          attempt_id TEXT PRIMARY KEY,
          question_id TEXT NOT NULL,
          question_revision INTEGER NOT NULL,
          selected_index INTEGER,
          confidence TEXT,
          perceived_difficulty TEXT,
          learning_gap INTEGER,
          feedback_json TEXT,
          created_at TEXT NOT NULL,
          synced_at TEXT,
          answered_offline INTEGER NOT NULL DEFAULT 0,
          offline_source TEXT
        );
        CREATE TABLE IF NOT EXISTS qf_offline_study_pack (
          position INTEGER PRIMARY KEY,
          pack_id TEXT NOT NULL,
          question_id TEXT NOT NULL,
          revision INTEGER NOT NULL,
          exam_project_id TEXT,
          generated_at TEXT NOT NULL,
          selection_policy TEXT,
          core_policy TEXT,
          consumed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_qf_outbox_created ON qf_outbox(created_at);
        CREATE INDEX IF NOT EXISTS idx_qf_offline_pack_question ON qf_offline_study_pack(question_id, revision);
        CREATE INDEX IF NOT EXISTS idx_qf_attempt_question ON qf_local_attempts(question_id, created_at);
      `);

      // Migração idempotente para instalações Mobile 0.11.x, cuja tabela de
      // tentativas ainda não distinguia respostas feitas sem conexão.
      const attemptColumns = await db.getAllAsync<{ name: string }>('PRAGMA table_info(qf_local_attempts)');
      const attemptColumnNames = new Set(attemptColumns.map((column) => String(column.name)));
      const addedOfflineColumn = !attemptColumnNames.has('answered_offline');
      if (addedOfflineColumn) {
        await db.execAsync('ALTER TABLE qf_local_attempts ADD COLUMN answered_offline INTEGER NOT NULL DEFAULT 0;');
      }
      if (!attemptColumnNames.has('offline_source')) {
        await db.execAsync('ALTER TABLE qf_local_attempts ADD COLUMN offline_source TEXT;');
      }
      // Na primeira migração, recupera tentativas antigas cujo envio já ocorreu,
      // mas cujo feedback ainda não tinha uma área própria no app. A marcação não
      // volta a rodar em aberturas futuras, evitando classificar tentativas online.
      if (addedOfflineColumn) {
        await db.execAsync(`
          UPDATE qf_local_attempts
          SET answered_offline=1, offline_source=COALESCE(NULLIF(offline_source,''),'legacy_pending_result')
          WHERE selected_index IS NOT NULL AND feedback_json IS NULL;
        `);
      }
      await db.execAsync(`
        CREATE INDEX IF NOT EXISTS idx_qf_attempt_offline_result
          ON qf_local_attempts(answered_offline, feedback_json, created_at);
      `);
      return db;
    });
  }
  return databasePromise;
}

export async function setMeta(key: string, value: string): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    'INSERT INTO qf_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
    key,
    value,
  );
}

export async function getMeta(key: string): Promise<string | null> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ value: string }>('SELECT value FROM qf_meta WHERE key=?', key);
  return row?.value ?? null;
}

export async function enqueueEvent(event: LearningEvent): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    'INSERT OR IGNORE INTO qf_outbox(event_id,event_json,created_at) VALUES(?,?,?)',
    event.event_id,
    JSON.stringify(event),
    new Date().toISOString(),
  );
}

export async function listOutbox(limit = 100): Promise<OutboxRow[]> {
  const db = await getDb();
  return db.getAllAsync<OutboxRow>(
    'SELECT event_id,event_json,created_at,attempts,last_error FROM qf_outbox ORDER BY created_at ASC LIMIT ?',
    Math.max(1, Math.min(500, limit)),
  );
}

export async function markOutboxError(eventIds: string[], message: string): Promise<void> {
  if (!eventIds.length) return;
  const db = await getDb();
  for (const id of eventIds) {
    await db.runAsync(
      'UPDATE qf_outbox SET attempts=attempts+1,last_error=? WHERE event_id=?',
      message.slice(0, 500),
      id,
    );
  }
}

export async function removeOutbox(eventIds: string[]): Promise<void> {
  if (!eventIds.length) return;
  const db = await getDb();
  for (const id of eventIds) {
    await db.runAsync('DELETE FROM qf_outbox WHERE event_id=?', id);
  }
}

export async function cacheQuestion(question: MobileQuestion): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO qf_question_cache(question_id,revision,payload_json,fetched_at)
     VALUES(?,?,?,?)
     ON CONFLICT(question_id,revision) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at`,
    question.question_id,
    question.question_revision,
    JSON.stringify(question),
    new Date().toISOString(),
  );
}

export async function getCachedQuestion(questionId: string, revision?: number): Promise<MobileQuestion | null> {
  const db = await getDb();
  const row = revision == null
    ? await db.getFirstAsync<{ payload_json: string }>(
        'SELECT payload_json FROM qf_question_cache WHERE question_id=? ORDER BY revision DESC LIMIT 1',
        questionId,
      )
    : await db.getFirstAsync<{ payload_json: string }>(
        'SELECT payload_json FROM qf_question_cache WHERE question_id=? AND revision=?',
        questionId,
        revision,
      );
  if (!row) return null;
  try { return JSON.parse(row.payload_json) as MobileQuestion; } catch { return null; }
}

export async function replaceOfflineStudyPack(pack: OfflineStudyPack): Promise<void> {
  const db = await getDb();
  const questions = Array.isArray(pack?.questions) ? pack.questions : [];
  await db.withTransactionAsync(async () => {
    await db.runAsync('DELETE FROM qf_offline_study_pack');
    for (let position = 0; position < questions.length; position += 1) {
      const question = questions[position];
      if (!question) continue;
      await db.runAsync(
        `INSERT INTO qf_question_cache(question_id,revision,payload_json,fetched_at)
         VALUES(?,?,?,?)
         ON CONFLICT(question_id,revision) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at`,
        question.question_id,
        question.question_revision,
        JSON.stringify(question),
        new Date().toISOString(),
      );
      await db.runAsync(
        `INSERT INTO qf_offline_study_pack(
          position,pack_id,question_id,revision,exam_project_id,generated_at,selection_policy,core_policy,consumed_at
        ) VALUES(?,?,?,?,?,?,?,?,NULL)`,
        position,
        String(pack.pack_id || ''),
        question.question_id,
        question.question_revision,
        String(pack.exam_project_id || ''),
        String(pack.generated_at || new Date().toISOString()),
        String(pack.selection_policy || ''),
        String(pack.core_policy || ''),
      );
    }
    await db.runAsync(
      'INSERT INTO qf_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
      'offline_study_pack_meta_v1',
      JSON.stringify({
        pack_id: String(pack.pack_id || ''),
        generated_at: String(pack.generated_at || ''),
        exam_project_id: String(pack.exam_project_id || ''),
        count: questions.length,
        source: String(pack.source || 'studio_learning_engine'),
        selection_policy: String(pack.selection_policy || ''),
        core_policy: String(pack.core_policy || ''),
      }),
    );
  });
}

export async function getOfflineStudyPackQuestions(): Promise<MobileQuestion[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<{ question_id: string; revision: number }>(
    `SELECT question_id,revision FROM qf_offline_study_pack
     WHERE consumed_at IS NULL ORDER BY position ASC`,
  );
  const result: MobileQuestion[] = [];
  for (const row of rows) {
    const question = await getCachedQuestion(row.question_id, row.revision);
    if (question) result.push(question);
  }
  return result;
}

export async function markOfflineStudyPackConsumed(questionId: string, revision: number): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    'UPDATE qf_offline_study_pack SET consumed_at=? WHERE question_id=? AND revision=? AND consumed_at IS NULL',
    new Date().toISOString(), questionId, revision,
  );
}

export async function offlineStudyPackInfo(): Promise<{ count: number; generated_at: string; pack_id: string; source: string } | null> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ total: number }>('SELECT COUNT(*) AS total FROM qf_offline_study_pack WHERE consumed_at IS NULL');
  const raw = await getMeta('offline_study_pack_meta_v1');
  if (!raw && !Number(row?.total || 0)) return null;
  let meta: any = {};
  try { meta = raw ? JSON.parse(raw) : {}; } catch { meta = {}; }
  return {
    count: Number(row?.total || 0),
    generated_at: String(meta.generated_at || ''),
    pack_id: String(meta.pack_id || ''),
    source: String(meta.source || 'studio_learning_engine'),
  };
}

export async function saveLocalAttempt(input: {
  attemptId: string;
  questionId: string;
  questionRevision: number;
  selectedIndex: number;
  confidence?: string;
  perceivedDifficulty?: string;
  learningGap?: boolean;
  answeredOffline?: boolean;
  offlineSource?: string;
}): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO qf_local_attempts(
      attempt_id,question_id,question_revision,selected_index,confidence,perceived_difficulty,learning_gap,created_at,answered_offline,offline_source
     ) VALUES(?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(attempt_id) DO UPDATE SET
       selected_index=excluded.selected_index,confidence=excluded.confidence,
       perceived_difficulty=excluded.perceived_difficulty,learning_gap=excluded.learning_gap,
       answered_offline=MAX(qf_local_attempts.answered_offline,excluded.answered_offline),
       offline_source=COALESCE(NULLIF(excluded.offline_source,''),qf_local_attempts.offline_source)`,
    input.attemptId,
    input.questionId,
    input.questionRevision,
    input.selectedIndex,
    input.confidence ?? null,
    input.perceivedDifficulty ?? null,
    input.learningGap == null ? null : input.learningGap ? 1 : 0,
    new Date().toISOString(),
    input.answeredOffline ? 1 : 0,
    String(input.offlineSource || ''),
  );
}

export async function markAttemptAnsweredOffline(attemptId: string, source = 'network_unavailable'): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `UPDATE qf_local_attempts
     SET answered_offline=1, offline_source=COALESCE(NULLIF(offline_source,''),?)
     WHERE attempt_id=?`,
    String(source || 'network_unavailable'),
    attemptId,
  );
}

export type OfflineAttemptHistoryItem = {
  attempt_id: string;
  question_id: string;
  question_revision: number;
  selected_index: number | null;
  confidence: string | null;
  perceived_difficulty: string | null;
  created_at: string;
  synced_at: string | null;
  offline_source: string;
  question: MobileQuestion | null;
  feedback: Feedback | null;
};

export async function listOfflineAttemptsAwaitingFeedback(limit = 50): Promise<Array<{ attempt_id: string }>> {
  const db = await getDb();
  return db.getAllAsync<{ attempt_id: string }>(
    `SELECT attempt_id FROM qf_local_attempts
     WHERE answered_offline=1 AND selected_index IS NOT NULL AND feedback_json IS NULL
     ORDER BY created_at ASC LIMIT ?`,
    Math.max(1, Math.min(100, limit)),
  );
}

export async function offlineAttemptHistoryInfo(): Promise<{ total: number; resolved: number; pending: number }> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ total: number; resolved: number; pending: number }>(
    `SELECT COUNT(*) AS total,
            SUM(CASE WHEN feedback_json IS NOT NULL THEN 1 ELSE 0 END) AS resolved,
            SUM(CASE WHEN feedback_json IS NULL THEN 1 ELSE 0 END) AS pending
     FROM qf_local_attempts WHERE answered_offline=1 AND selected_index IS NOT NULL`,
  );
  return {
    total: Number(row?.total || 0),
    resolved: Number(row?.resolved || 0),
    pending: Number(row?.pending || 0),
  };
}

export async function listOfflineAttemptHistory(limit = 100): Promise<OfflineAttemptHistoryItem[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<any>(
    `SELECT attempt_id,question_id,question_revision,selected_index,confidence,perceived_difficulty,
            feedback_json,created_at,synced_at,COALESCE(offline_source,'') AS offline_source
     FROM qf_local_attempts
     WHERE answered_offline=1 AND selected_index IS NOT NULL
     ORDER BY created_at DESC LIMIT ?`,
    Math.max(1, Math.min(250, limit)),
  );
  const result: OfflineAttemptHistoryItem[] = [];
  for (const row of rows) {
    let feedback: Feedback | null = null;
    try { feedback = row.feedback_json ? JSON.parse(String(row.feedback_json)) as Feedback : null; } catch { feedback = null; }
    result.push({
      attempt_id: String(row.attempt_id || ''),
      question_id: String(row.question_id || ''),
      question_revision: Number(row.question_revision || 1),
      selected_index: row.selected_index == null ? null : Number(row.selected_index),
      confidence: row.confidence == null ? null : String(row.confidence),
      perceived_difficulty: row.perceived_difficulty == null ? null : String(row.perceived_difficulty),
      created_at: String(row.created_at || ''),
      synced_at: row.synced_at == null ? null : String(row.synced_at),
      offline_source: String(row.offline_source || ''),
      question: await getCachedQuestion(String(row.question_id || ''), Number(row.question_revision || 1)),
      feedback,
    });
  }
  return result;
}


export async function getLocalAttempt(attemptId: string): Promise<{
  attempt_id: string; feedback_json: string | null; selected_index: number | null; confidence: string | null; perceived_difficulty: string | null;
} | null> {
  const db = await getDb();
  return db.getFirstAsync<any>(
    'SELECT attempt_id,feedback_json,selected_index,confidence,perceived_difficulty FROM qf_local_attempts WHERE attempt_id=?',
    attemptId,
  );
}

export async function saveFeedback(attemptId: string, feedback: unknown): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    'UPDATE qf_local_attempts SET feedback_json=?,synced_at=? WHERE attempt_id=?',
    JSON.stringify(feedback),
    new Date().toISOString(),
    attemptId,
  );
}

export async function outboxCount(): Promise<number> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ total: number }>('SELECT COUNT(*) AS total FROM qf_outbox');
  return Number(row?.total || 0);
}

export async function resetLocalStudyData(): Promise<void> {
  const db = await getDb();
  await db.execAsync('DELETE FROM qf_outbox; DELETE FROM qf_offline_study_pack; DELETE FROM qf_question_cache; DELETE FROM qf_local_attempts; DELETE FROM qf_meta;');
}
