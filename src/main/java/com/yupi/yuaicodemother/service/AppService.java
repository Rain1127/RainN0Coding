package com.yupi.yuaicodemother.service;

import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.model.dto.app.AppAddRequest;
import com.yupi.yuaicodemother.model.dto.app.AppQueryRequest;
import com.yupi.yuaicodemother.model.entity.App;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.model.vo.AppVO;
import reactor.core.publisher.Flux;

import java.util.List;

/**
 * 应用 服务层。
 *
 * @author <a>Rain</a>
 */
public interface AppService extends IService<App> {

    /**
     * 获取应用封装类
     *
     * @param app 应用实体对象
     * @return 应用封装类
     */
    AppVO getAppVO(App app) ;


    /**
     * 批量获取应用封装类列表
     *
     * @param appList 应用实体列表
     * @return 应用封装类列表
     */
    List<AppVO> getAppVOList(List<App> appList);

    /**
     * 构造应用分页查询条件
     * @param appQueryRequest
     * @return
     */
    QueryWrapper getQueryWrapper(AppQueryRequest appQueryRequest) ;

    /**
     * 对话生成应用代码
     * @param appId 应用id
     * @param message 对话消息
     * @param loginUser 登录用户
     * @return 代码流
     */
    Flux<String> chatToGenCode(Long appId,String message,User loginUser);

    Flux<String> chatToGenCode(Long appId, String message, User loginUser, String requestId, String idempotencyKey);

    /**
     * 创建应用
     * @param appAddRequest 创建应用请求参数
     * @param loginUser 登录用户
     * @return 应用id
     */
    Long createApp(AppAddRequest appAddRequest, User loginUser);

    /**
     * 部署应用
     * @param appId 应用id
     * @param loginUser 登录用户
     * @return 部署结果
     */
    String deployApp(Long appId,User loginUser);
}
