package com.rain.rainn0coding.service.impl;

import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.AppVersion;
import com.rain.rainn0coding.mapper.AppVersionMapper;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.AppVersionService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.RequestParam;

import java.time.LocalDateTime;

/**
 *  服务层实现。
 *
 * @author <a>Rain</a>
 */
@Service
public class AppVersionServiceImpl extends ServiceImpl<AppVersionMapper, AppVersion>  implements AppVersionService{

    @Resource
    private AppService appService;

    /**
     * 在APP创建完成之后，更新APP版本。
     * @param appId
     * @param codeContent
     * @param description
     * @return
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppVersion createNewVersion(Long appId, String codeContent, String description) {
        // 检查应用是否存在
        App app = appService.getById(appId);
        if (app == null) {
            throw new BusinessException(ErrorCode.NOT_FOUND_ERROR, "应用不存在");
        }
        Integer currentVersion = app.getCurrentVersion();
        Long id = app.getId();

        AppVersion appVersion = new AppVersion();
        appVersion.setAppId(appId);
        appVersion.setId(id);
        appVersion.setVersionNumber(currentVersion + 1);
        return appVersion;
    }

}
