-- Additive migration; run once before enabling the queue. No existing tables are modified.
CREATE TABLE IF NOT EXISTS generation_queue_lock (id INT PRIMARY KEY, paused INT NOT NULL DEFAULT 0);
INSERT IGNORE INTO generation_queue_lock(id) VALUES (1);
CREATE TABLE IF NOT EXISTS generation_task (
 task_id VARCHAR(36) PRIMARY KEY,
 app_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
 prompt LONGTEXT NOT NULL, code_gen_type VARCHAR(32) NOT NULL,
 idempotency_key VARCHAR(128) NOT NULL, trace_id VARCHAR(128),
 status VARCHAR(16) NOT NULL, active_app_id BIGINT NULL,
 owner_id VARCHAR(36), error_message VARCHAR(1000),
 last_event_id BIGINT NOT NULL DEFAULT 0,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 started_at TIMESTAMP NULL, ended_at TIMESTAMP NULL,
 UNIQUE KEY uq_generation_request(user_id,app_id,idempotency_key),
 UNIQUE KEY uq_generation_active_app(active_app_id),
 INDEX ix_generation_status(status,created_at),
 INDEX ix_generation_app(app_id,user_id,created_at)
);
CREATE TABLE IF NOT EXISTS generation_event (
 task_id VARCHAR(36) NOT NULL, event_id BIGINT NOT NULL,
 data LONGTEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(task_id,event_id)
);
CREATE TABLE IF NOT EXISTS generation_outbox (
 task_id VARCHAR(36) PRIMARY KEY, app_id BIGINT NOT NULL,
 published INT NOT NULL DEFAULT 0, attempts INT NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX ix_generation_dispatch(published,next_attempt_at)
);
