package com.rain.rainn0coding.service;

import com.mybatisflex.core.service.IService;
import com.rain.rainn0coding.model.entity.AppVersion;

/**
 *  服务层。
 *
 * @author <a>Rain</a>
 */
public interface AppVersionService extends IService<AppVersion> {
    AppVersion createNewVersion(Long appId,String codeContent,String description);
}
