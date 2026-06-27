package com.yupi.yuaicodemother.utils;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class SqlSafetyUtilsTest {

    @Test
    void allowOnlyWhitelistedSortFields() {
        Set<String> allowedFields = Set.of("id", "createTime", "editTime");

        assertEquals("createTime", SqlSafetyUtils.safeSortField("createTime", allowedFields));
        assertNull(SqlSafetyUtils.safeSortField("createTime desc; drop table user", allowedFields));
        assertNull(SqlSafetyUtils.safeSortField("userName", allowedFields));
        assertNull(SqlSafetyUtils.safeSortField("", allowedFields));
    }
}
