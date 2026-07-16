-- Repeatable MySQL 8 migration for databases created before intent_config
-- adopted the MyBatis-compatible snake_case column contract.

SET @migration_schema = DATABASE();

SET @migration_sql = IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'configName')
  AND NOT EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'config_name'),
  'ALTER TABLE `intent_config` CHANGE COLUMN `configName` `config_name` VARCHAR(64) DEFAULT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @migration_sql = IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'treeJson')
  AND NOT EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'tree_json'),
  'ALTER TABLE `intent_config` CHANGE COLUMN `treeJson` `tree_json` LONGTEXT DEFAULT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @migration_sql = IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'updatedBy')
  AND NOT EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'updated_by'),
  'ALTER TABLE `intent_config` CHANGE COLUMN `updatedBy` `updated_by` BIGINT DEFAULT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @migration_sql = IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'createTime')
  AND NOT EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'create_time'),
  'ALTER TABLE `intent_config` CHANGE COLUMN `createTime` `create_time` DATETIME DEFAULT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @migration_sql = IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'updateTime')
  AND NOT EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @migration_schema AND TABLE_NAME = 'intent_config' AND COLUMN_NAME = 'update_time'),
  'ALTER TABLE `intent_config` CHANGE COLUMN `updateTime` `update_time` DATETIME DEFAULT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
