package com.yupi.yuaicodemother.utils;

import cn.hutool.core.util.StrUtil;

import java.util.Set;

public final class SqlSafetyUtils {

    private SqlSafetyUtils() {
    }

    public static String safeSortField(String sortField, Set<String> allowedFields) {
        if (StrUtil.isBlank(sortField) || allowedFields == null || !allowedFields.contains(sortField)) {
            return null;
        }
        return sortField;
    }
}
