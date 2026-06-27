package com.yupi.yuaicodemother.service;

import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.model.entity.IntentConfig;

public interface IntentConfigService extends IService<IntentConfig> {

    /** 获取当前生效的意图树 JSON */
    String getActiveTreeJson();

    /** 保存或更新自定义意图树 */
    void saveCustomTree(String treeJson, Long userId);
}
