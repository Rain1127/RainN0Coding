package com.rain.rainn0coding.model.entity;

import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 意图树配置 —— 管理员可自定义意图分类树。
 */
@Table("intent_config")
@Data
public class IntentConfig {

    @Id(keyType = KeyType.Auto)
    private Long id;

    /** 配置名称，如 "default" 或 "admin_custom" */
    private String configName;

    /** 意图树 JSON（完整树结构） */
    private String treeJson;

    /** 更新人 */
    private Long updatedBy;

    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
