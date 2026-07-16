-- Database bootstrap for local development and tests
CREATE DATABASE IF NOT EXISTS rainn0coding
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE rainn0coding;

CREATE TABLE IF NOT EXISTS `user` (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  userAccount VARCHAR(256) NOT NULL,
  userPassword VARCHAR(512) NOT NULL,
  userName VARCHAR(256) DEFAULT NULL,
  userAvatar VARCHAR(1024) DEFAULT NULL,
  userProfile VARCHAR(512) DEFAULT NULL,
  userRole VARCHAR(256) NOT NULL DEFAULT 'user',
  editTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  createTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updateTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  isDelete TINYINT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_userAccount (userAccount),
  KEY idx_userName (userName)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  appName VARCHAR(256) DEFAULT NULL,
  cover VARCHAR(512) DEFAULT NULL,
  initPrompt TEXT DEFAULT NULL,
  codeGenType VARCHAR(64) DEFAULT NULL,
  deployKey VARCHAR(64) DEFAULT NULL,
  deployedTime DATETIME DEFAULT NULL,
  priority INT NOT NULL DEFAULT 0,
  userId BIGINT NOT NULL,
  editTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  createTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updateTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  isDelete TINYINT NOT NULL DEFAULT 0,
  currentVersion INT DEFAULT NULL,
  UNIQUE KEY uk_deployKey (deployKey),
  KEY idx_appName (appName),
  KEY idx_userId (userId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  message TEXT NOT NULL,
  messageType VARCHAR(32) NOT NULL,
  appId BIGINT NOT NULL,
  userId BIGINT NOT NULL,
  createTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updateTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  isDelete TINYINT NOT NULL DEFAULT 0,
  KEY idx_appId (appId),
  KEY idx_createTime (createTime),
  KEY idx_appId_createTime (appId, createTime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS intent_config (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  `config_name` VARCHAR(64) DEFAULT NULL,
  `tree_json` LONGTEXT DEFAULT NULL,
  `updated_by` BIGINT DEFAULT NULL,
  `create_time` DATETIME DEFAULT NULL,
  `update_time` DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Existing installations created with camelCase intent_config columns must run
-- sql/migrate_intent_config_snake_case.sql once before starting the upgraded service.

CREATE TABLE IF NOT EXISTS app_version (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  app_id BIGINT DEFAULT NULL,
  version_number INT DEFAULT NULL,
  code_content LONGTEXT DEFAULT NULL,
  description VARCHAR(1024) DEFAULT NULL,
  create_time DATETIME DEFAULT NULL,
  KEY idx_app_id (app_id),
  KEY idx_version_number (version_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
