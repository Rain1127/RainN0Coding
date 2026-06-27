package com.yupi.yuaicodemother.service;

import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.model.entity.AppVersion;

/**
 *  服务层。
 *
 * @author <a>Rain</a>
 */
public interface AppVersionService extends IService<AppVersion> {
    AppVersion createNewVersion(Long appId,String codeContent,String description);
}
