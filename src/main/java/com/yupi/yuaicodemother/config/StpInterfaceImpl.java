package com.yupi.yuaicodemother.config;

import cn.dev33.satoken.stp.StpInterface;
import com.yupi.yuaicodemother.mapper.UserMapper;
import com.yupi.yuaicodemother.model.entity.User;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Sa-Token 权限与角色数据源。
 * 为 @SaCheckRole / StpUtil.checkRole() 提供角色查询。
 */
@Component
public class StpInterfaceImpl implements StpInterface {

    @Resource
    private UserMapper userMapper;

    @Override
    public List<String> getPermissionList(Object loginId, String loginType) {
        // 本项目仅使用角色（admin / user），不使用权限码
        return List.of();
    }

    @Override
    public List<String> getRoleList(Object loginId, String loginType) {
        User user = userMapper.selectOneById(Long.valueOf(loginId.toString()));
        if (user == null) {
            return List.of();
        }
        return List.of(user.getUserRole());
    }
}
