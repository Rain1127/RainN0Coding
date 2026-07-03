package com.yupi.yuaicodemother.config;

import com.mybatisflex.core.query.QueryWrapper;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;

/**
 * 数据初始化，确保系统启动后存在默认管理员账号。
 */
@Component
@Slf4j
public class DataInitializer {

    @Resource
    private UserService userService;

    @PostConstruct
    public void initAdminUser() {
        try {
            QueryWrapper queryWrapper = QueryWrapper.create()
                    .eq("userAccount", "admin");
            User existing = userService.getOne(queryWrapper);
            if (existing != null) {
                log.info("管理员账号已存在: admin");
                return;
            }

            User admin = new User();
            admin.setUserAccount("admin");
            // MD5("rainadmin123") = 4019b808b8a10fae1eeb8d0eec9a4c93
            admin.setUserPassword("4019b808b8a10fae1eeb8d0eec9a4c93");
            admin.setUserName("管理员");
            admin.setUserRole("admin");
            admin.setUserProfile("系统管理员");
            userService.save(admin);
            log.info("已创建默认管理员: admin / admin123");
        } catch (DataAccessException e) {
            log.warn(
                    "Skip admin initialization because database is unavailable. " +
                            "Please verify MYSQL_URL / MYSQL_USERNAME / MYSQL_PASSWORD or initialize the local database first. " +
                            "Root cause: {}",
                    e.getMessage()
            );
        }
    }
}
