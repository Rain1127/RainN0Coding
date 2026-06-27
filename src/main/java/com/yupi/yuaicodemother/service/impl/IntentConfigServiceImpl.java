package com.yupi.yuaicodemother.service.impl;

import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.yupi.yuaicodemother.mapper.IntentConfigMapper;
import com.yupi.yuaicodemother.model.entity.IntentConfig;
import com.yupi.yuaicodemother.service.IntentConfigService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class IntentConfigServiceImpl
        extends ServiceImpl<IntentConfigMapper, IntentConfig>
        implements IntentConfigService {

    @Resource
    private IntentConfigMapper intentConfigMapper;

    @Override
    public String getActiveTreeJson() {
        QueryWrapper qw = QueryWrapper.create()
                .eq("config_name", "admin_custom")
                .orderBy("update_time", false);
        IntentConfig config = intentConfigMapper.selectOneByQuery(qw);
        if (config != null) {
            return config.getTreeJson();
        }
        return null; // 返回 null，表示使用默认树
    }

    @Override
    public void saveCustomTree(String treeJson, Long userId) {
        QueryWrapper qw = QueryWrapper.create()
                .eq("config_name", "admin_custom");
        IntentConfig existing = intentConfigMapper.selectOneByQuery(qw);

        if (existing != null) {
            existing.setTreeJson(treeJson);
            existing.setUpdatedBy(userId);
            existing.setUpdateTime(LocalDateTime.now());
            intentConfigMapper.update(existing);
        } else {
            IntentConfig config = new IntentConfig();
            config.setConfigName("admin_custom");
            config.setTreeJson(treeJson);
            config.setUpdatedBy(userId);
            config.setCreateTime(LocalDateTime.now());
            config.setUpdateTime(LocalDateTime.now());
            intentConfigMapper.insert(config);
        }
    }
}
