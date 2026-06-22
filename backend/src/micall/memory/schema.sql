-- MiCall 存储 schema（docs/02 §3.1 / §6 / §6.1）。Postgres + pgvector。
-- 铁律7：角色定义（出厂，全用户共享）与用户关系（per-user，挂 character_id）严格分离。
-- 事实层与理解层物理分开（§3.1）。

CREATE EXTENSION IF NOT EXISTS vector;

-- ───────────────────────── 出厂角色（共享，只读）─────────────────────────
-- 角色本体是资产管线的 spec（docs/01）；这里存其运行时副本 + 版本。
CREATE TABLE IF NOT EXISTS characters (
    character_id   TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    version        TEXT NOT NULL,
    spec           JSONB NOT NULL,           -- 完整角色 spec（persona/voice/visual…）
    voice_id       TEXT NOT NULL DEFAULT '',
    emotion_map    JSONB NOT NULL DEFAULT '{}',
    autonomous     JSONB NOT NULL DEFAULT '{}', -- 尺度四 §4.1 自主状态（独立于用户）
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ───────────────────────────── 用户 ─────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id            TEXT PRIMARY KEY,
    email              TEXT UNIQUE,
    remaining_seconds  INTEGER NOT NULL DEFAULT 0,  -- 服务端权威计费余额（§5）
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────── 事实层（客观、只增、可检索 · pgvector）───────────────────
CREATE TABLE IF NOT EXISTS facts (
    id             BIGSERIAL PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    character_id   TEXT NOT NULL REFERENCES characters(character_id),
    text           TEXT NOT NULL,
    embedding      vector(1024),                 -- text-embedding-v3 维度（按实际模型调整）
    emotion_weight REAL NOT NULL DEFAULT 1.0,     -- 情感权重，进检索打分
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS facts_user_char_idx ON facts (user_id, character_id);
-- 语义检索（余弦）。真实可换 HNSW：USING hnsw (embedding vector_cosine_ops)。
CREATE INDEX IF NOT EXISTS facts_embedding_idx ON facts USING ivfflat (embedding vector_cosine_ops);

-- ─────────────── 理解层（主观、持续修正、有置信度 · 结构化 JSONB）───────────────
-- per-user × per-character。整块注入，不需向量。
CREATE TABLE IF NOT EXISTS user_profile (
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    character_id   TEXT NOT NULL REFERENCES characters(character_id),
    profile        JSONB NOT NULL DEFAULT '{}',  -- §3.2：fact_profile/personality_model/
                                                 --        interaction_prefs/open_hypotheses/relationship
    next_strategy  TEXT NOT NULL DEFAULT '',     -- §3.3 理解引擎产出的本轮对话策略
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, character_id)
);

-- ─────────────── 用户自定义音色（§6.1 三级覆盖的"用户自定义"层）───────────────
CREATE TABLE IF NOT EXISTS user_voice (
    user_id      TEXT NOT NULL REFERENCES users(user_id),
    character_id TEXT NOT NULL REFERENCES characters(character_id),
    voice_id     TEXT NOT NULL,
    label        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, character_id)
);

-- ───────────────────────── 通话记录 + 计费流水 ─────────────────────────
CREATE TABLE IF NOT EXISTS calls (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(user_id),
    character_id     TEXT NOT NULL REFERENCES characters(character_id),
    scenario         TEXT NOT NULL DEFAULT '',
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    ended_reason     TEXT NOT NULL DEFAULT ''      -- ended / out_of_minutes / call_failed
);

CREATE TABLE IF NOT EXISTS billing_ledger (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    delta_seconds INTEGER NOT NULL,                -- 负=消费，正=充值/赠送
    reason        TEXT NOT NULL,                   -- call / recharge / invite_reward / register_gift
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
