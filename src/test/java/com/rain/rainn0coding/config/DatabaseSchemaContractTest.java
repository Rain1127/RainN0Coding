package com.rain.rainn0coding.config;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DatabaseSchemaContractTest {

    @Test
    void intentConfigColumnsMatchMyBatisSnakeCaseMapping() throws IOException {
        String schema = Files.readString(Path.of("sql", "create_table.sql"));

        for (String column : new String[]{
                "config_name", "tree_json", "updated_by", "create_time", "update_time"
        }) {
            assertTrue(schema.contains("`" + column + "`"),
                    () -> "intent_config schema must declare column " + column);
        }
        assertFalse(schema.contains("configName"));
        assertFalse(schema.contains("treeJson"));
    }

    @Test
    void existingCamelCaseIntentConfigSchemaHasRepeatableMigration() throws IOException {
        String migration = Files.readString(Path.of("sql", "migrate_intent_config_snake_case.sql"));

        assertTrue(migration.contains("INFORMATION_SCHEMA.COLUMNS"));
        assertTrue(migration.contains("PREPARE migration_stmt"));
        for (String[] columns : new String[][]{
                {"configName", "config_name"},
                {"treeJson", "tree_json"},
                {"updatedBy", "updated_by"},
                {"createTime", "create_time"},
                {"updateTime", "update_time"}
        }) {
            assertTrue(migration.contains("`" + columns[0] + "`"));
            assertTrue(migration.contains("`" + columns[1] + "`"));
        }
    }
}
