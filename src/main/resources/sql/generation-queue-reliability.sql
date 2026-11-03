-- Run after generation-queue.sql, before upgrading Java. Safe to run again.
CREATE TABLE IF NOT EXISTS generation_execution (
 task_id VARCHAR(36) PRIMARY KEY,
 heartbeat_at TIMESTAMP(6) NULL, lease_until TIMESTAMP(6) NULL,
 retries INT NOT NULL DEFAULT 0, recoverable INT NOT NULL DEFAULT 0,
 failure_kind VARCHAR(16) NULL, finalized INT NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE IF NOT EXISTS generation_failure (
 failure_key VARCHAR(256) PRIMARY KEY, task_id VARCHAR(36) NULL,
 reason VARCHAR(64) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX ix_generation_failure_task(task_id,created_at)
);
