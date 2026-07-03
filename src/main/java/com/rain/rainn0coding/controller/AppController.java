package com.rain.rainn0coding.controller;


import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.convert.Convert;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.rain.rainn0coding.annotation.AuthCheck;
import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.DeleteRequest;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.config.IdempotencyProperties;
import com.rain.rainn0coding.constant.AppConstant;
import com.rain.rainn0coding.constant.UserConstant;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.ThrowUtils;
import com.rain.rainn0coding.idempotency.IdempotencyDecision;
import com.rain.rainn0coding.idempotency.IdempotencyRecord;
import com.rain.rainn0coding.idempotency.IdempotencyService;
import com.rain.rainn0coding.model.dto.app.*;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import com.rain.rainn0coding.model.vo.AppVO;
import com.rain.rainn0coding.ratelimiter.annotation.RateLimit;
import com.rain.rainn0coding.ratelimiter.enums.RateLimitType;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.ProjectDownloadService;
import com.rain.rainn0coding.service.UserService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.awt.*;
import java.io.File;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 应用 控制层。
 *
 * @author <a>Rain</a>
 */
@RestController
@RequestMapping("/app")
public class AppController {

    private static final long USER_PAGE_SIZE_LIMIT = 20;

    private static final long MAX_PAGE_SIZE = 50;

    @Resource
    private AppService appService;

    @Resource
    private UserService userService;

    @Resource
    private ProjectDownloadService projectDownloadService;

    @Resource
    private IdempotencyService idempotencyService;

    @Resource
    private IdempotencyProperties idempotencyProperties;


    /**
     * 聊天生成应用代码
     *
     * @param appId   应用 id
     * @param message 消息
     * @param request 请求
     * @return 代码
     */
    @GetMapping(value = "/chat/gen/code",produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @RateLimit(limitType = RateLimitType.USER, rate = 5, rateInterval = 60, message = "AI对话请求过于频繁，请稍后再试")
    public Flux<ServerSentEvent<String>> chatToGenCode(@RequestParam Long appId,
                                    @RequestParam String message,
                                    @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                    HttpServletRequest request) {
        //produces = MediaType.TEXT_EVENT_STREAM_VALUE:(SSE 流式返回)
        //1.参数校验
        ThrowUtils.throwIf(appId == null || appId <= 0, ErrorCode.PARAMS_ERROR, "应用id错误");
        ThrowUtils.throwIf(StrUtil.isBlank(message), ErrorCode.PARAMS_ERROR, "消息不能为空");
        //2.获取当前登录用户
        User loginUser = userService.getLoginUser(request);
        String requestId = StrUtil.isNotBlank(idempotencyKey) ? idempotencyKey : UUID.randomUUID().toString();
        String fingerprint = idempotencyService.fingerprint("app:chat:gen-code", appId, message);
        IdempotencyDecision decision = idempotencyService.start(
                "app:chat:gen-code", loginUser.getId(), idempotencyKey, fingerprint, idempotencyProperties.aiProcessingTtl());
        if (decision.type() == IdempotencyDecision.Type.IN_PROGRESS) {
            return duplicateSse("duplicate_in_progress");
        }
        if (decision.type() == IdempotencyDecision.Type.REPLAY_SUCCESS) {
            return duplicateSse("duplicate_completed");
        }
        if (decision.type() == IdempotencyDecision.Type.REPLAY_FAILED) {
            return failedReplaySse(decision.record());
        }
        if (decision.type() == IdempotencyDecision.Type.FINGERPRINT_MISMATCH) {
            throw new BusinessException(ErrorCode.REQUEST_REPLAY_CONFLICT);
        }
        //3.调用服务，生成代码 (SSE 流式返回)
        Flux<String> contentFlux;
        try {
            contentFlux = appService.chatToGenCode(appId, message, loginUser, requestId, idempotencyKey);
        } catch (BusinessException e) {
            idempotencyService.markFailed(decision.redisKey(), fingerprint, e.getCode(), e.getMessage());
            throw e;
        }
        AtomicReference<SseFailure> semanticFailure = new AtomicReference<>();
        return contentFlux
                .map(chunk->{
                    SseFailure failure = detectSemanticFailure(chunk);
                    if (failure != null) {
                        semanticFailure.compareAndSet(null, failure);
                    }
                    //解决了返回内容缺省问题
                    Map<String,String> wrapper = Map.of("d",chunk);
                    String jsonData = JSONUtil.toJsonStr(wrapper);
                    return ServerSentEvent.<String>builder()
                            .data(jsonData)
                            .build();
                })
                .doOnComplete(() -> {
                    SseFailure failure = semanticFailure.get();
                    if (failure != null) {
                        idempotencyService.markFailed(decision.redisKey(), fingerprint,
                                failure.errorCode(), failure.message());
                    } else {
                        idempotencyService.markSuccess(decision.redisKey(), fingerprint,
                                JSONUtil.toJsonStr(Map.of("type", "done", "status", "success")), 200);
                    }
                })
                .doOnError(throwable -> idempotencyService.markFailed(decision.redisKey(), fingerprint,
                        throwable instanceof BusinessException businessException
                                ? businessException.getCode()
                                : ErrorCode.SYSTEM_ERROR.getCode(),
                        throwable.getMessage()))
                // 合并结束事件
                .concatWith(Mono.just(
                        //发送结束事件
                        ServerSentEvent.<String>builder()
                                .event("done")
                                .data("")//返回空数据，表示事件已经结束
                                .build()
                ));
    }

    /**
     * 应用部署
     *
     * @param appDeployRequest 部署请求
     * @param request          请求
     * @return 部署 URL
     */
    @PostMapping("/deploy")
    @RateLimit(limitType = RateLimitType.USER, rate = 10, rateInterval = 60, message = "部署请求过于频繁，请稍后再试")
    public BaseResponse<String> deployApp(@RequestBody AppDeployRequest appDeployRequest,
                                          @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                          HttpServletRequest request) {
        ThrowUtils.throwIf(appDeployRequest == null, ErrorCode.PARAMS_ERROR);
        Long appId = appDeployRequest.getAppId();
        ThrowUtils.throwIf(appId == null || appId <= 0, ErrorCode.PARAMS_ERROR, "应用 ID 不能为空");
        // 获取当前登录用户
        User loginUser = userService.getLoginUser(request);
        // 调用服务部署应用
        String fingerprint = idempotencyService.fingerprint("app:deploy", appId);
        IdempotencyDecision decision = idempotencyService.start(
                "app:deploy", loginUser.getId(), idempotencyKey, fingerprint, idempotencyProperties.processingTtl());
        BaseResponse<String> replay = replayResponse(decision, String.class);
        if (replay != null) {
            return replay;
        }
        replayFailed(decision);
        rejectActiveOrConflictingReplay(decision);
        try {
            String deployUrl = appService.deployApp(appId, loginUser);
            BaseResponse<String> response = ResultUtils.success(deployUrl);
            idempotencyService.markSuccess(decision.redisKey(), fingerprint, JSONUtil.toJsonStr(response), 200);
            return response;
        } catch (BusinessException e) {
            idempotencyService.markFailed(decision.redisKey(), fingerprint, e.getCode(), e.getMessage());
            throw e;
        } catch (RuntimeException e) {
            idempotencyService.markFailed(decision.redisKey(), fingerprint,
                    ErrorCode.SYSTEM_ERROR.getCode(), systemErrorMessage(e));
            throw e;
        }
    }



    /**
     * 下载应用代码
     *
     * @param appId    应用ID
     * @param request  请求
     * @param response 响应
     */
    @GetMapping("/download/{appId}")
    @RateLimit(limitType = RateLimitType.USER, rate = 20, rateInterval = 60, message = "下载请求过于频繁，请稍后再试")
    public void downloadAppCode(@PathVariable Long appId,
                                HttpServletRequest request,
                                HttpServletResponse response) {
        // 1. 基础校验
        ThrowUtils.throwIf(appId == null || appId <= 0, ErrorCode.PARAMS_ERROR, "应用ID无效");
        // 2. 查询应用信息
        App app = appService.getById(appId);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR, "应用不存在");
        // 3. 权限校验：只有应用创建者可以下载代码
        User loginUser = userService.getLoginUser(request);
        if (!app.getUserId().equals(loginUser.getId())) {
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR, "无权限下载该应用代码");
        }
        // 4. 构建应用代码目录路径（生成目录，非部署目录）
        String codeGenType = app.getCodeGenType();
        String sourceDirName = codeGenType + "_" + appId;
        String sourceDirPath = AppConstant.CODE_OUTPUT_ROOT_DIR + File.separator + sourceDirName;
        // 5. 检查代码目录是否存在
        File sourceDir = new File(sourceDirPath);
        ThrowUtils.throwIf(!sourceDir.exists() || !sourceDir.isDirectory(),
                ErrorCode.NOT_FOUND_ERROR, "应用代码不存在，请先生成代码");
        // 6. 生成下载文件名（不建议添加中文内容）
        String downloadFileName = String.valueOf(appId);
        // 7. 调用通用下载服务
        projectDownloadService.downloadProjectAsZip(sourceDirPath, downloadFileName, response);
    }


    /**
     * 创建应用
     *
     * @param appAddRequest 创建应用请求参数
     * @param request       请求
     * @return 应用ID
     */
    @PostMapping("/add")
    @RateLimit(limitType = RateLimitType.USER, rate = 30, rateInterval = 60, message = "创建应用过于频繁，请稍后再试")
    public BaseResponse<Long> addApp(@RequestBody AppAddRequest appAddRequest,
                                     @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                     HttpServletRequest request) {
        ThrowUtils.throwIf(appAddRequest == null, ErrorCode.PARAMS_ERROR);
        // 获取当前登录用户
        User loginUser = userService.getLoginUser(request);
        String fingerprint = idempotencyService.fingerprint("app:add", appAddRequest.getInitPrompt());
        IdempotencyDecision decision = idempotencyService.start(
                "app:add", loginUser.getId(), idempotencyKey, fingerprint, idempotencyProperties.processingTtl());
        BaseResponse<Long> replay = replayResponse(decision, Long.class);
        if (replay != null) {
            return replay;
        }
        replayFailed(decision);
        rejectActiveOrConflictingReplay(decision);
        try {
            Long appId = appService.createApp(appAddRequest, loginUser);
            BaseResponse<Long> response = ResultUtils.success(appId);
            idempotencyService.markSuccess(decision.redisKey(), fingerprint, JSONUtil.toJsonStr(response), 200);
            return response;
        } catch (BusinessException e) {
            idempotencyService.markFailed(decision.redisKey(), fingerprint, e.getCode(), e.getMessage());
            throw e;
        } catch (RuntimeException e) {
            idempotencyService.markFailed(decision.redisKey(), fingerprint,
                    ErrorCode.SYSTEM_ERROR.getCode(), systemErrorMessage(e));
            throw e;
        }
    }



    /**
     * 删除应用（用户只能删除自己的应用）
     *
     * @param deleteRequest 删除请求
     * @param request       请求
     * @return 删除结果
     */
    @PostMapping("/delete")
    public BaseResponse<Boolean> deleteApp(@RequestBody DeleteRequest deleteRequest, HttpServletRequest request) {
        if (deleteRequest == null || deleteRequest.getId() <= 0) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        User loginUser = userService.getLoginUser(request);
        long id = deleteRequest.getId();
        // 判断是否存在
        App oldApp = appService.getById(id);
        ThrowUtils.throwIf(oldApp == null, ErrorCode.NOT_FOUND_ERROR);
        // 仅本人或管理员可删除
        if (!oldApp.getUserId().equals(loginUser.getId()) && !UserConstant.ADMIN_ROLE.equals(loginUser.getUserRole())) {
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        }
        boolean result = appService.removeById(id);
        return ResultUtils.success(result);
    }


    /**
     * 更新应用（用户只能更新自己的应用名称）
     *
     * @param appUpdateRequest 更新请求
     * @param request          请求
     * @return 更新结果
     */
    @PostMapping("/update")
    public BaseResponse<Boolean> updateApp(@RequestBody AppUpdateRequest appUpdateRequest, HttpServletRequest request) {
        if (appUpdateRequest == null || appUpdateRequest.getId() == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        User loginUser = userService.getLoginUser(request);
        long id = appUpdateRequest.getId();
        // 判断是否存在
        App oldApp = appService.getById(id);
        ThrowUtils.throwIf(oldApp == null, ErrorCode.NOT_FOUND_ERROR);
        // 仅本人可更新
        if (!oldApp.getUserId().equals(loginUser.getId())) {
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        }
        App app = new App();
        app.setId(id);
        app.setAppName(appUpdateRequest.getAppName());
        // 设置编辑时间
        app.setEditTime(LocalDateTime.now());
        boolean result = appService.updateById(app);
        ThrowUtils.throwIf(!result, ErrorCode.OPERATION_ERROR);
        return ResultUtils.success(true);
    }


    /**
     * 根据 id 获取应用详情
     *
     * @param id      应用 id
     * @return 应用详情
     */
    @GetMapping("/get/vo")
    public BaseResponse<AppVO> getAppVOById(long id) {
        ThrowUtils.throwIf(id <= 0, ErrorCode.PARAMS_ERROR);
        // 查询数据库
        App app = appService.getById(id);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR);
        // 获取封装类（包含用户信息）
        return ResultUtils.success(appService.getAppVO(app));
    }


    /**
     * 分页获取当前用户创建的应用列表
     *
     * @param appQueryRequest 查询请求
     * @param request         请求
     * @return 应用列表
     */
    @PostMapping("/my/list/page/vo")
    public BaseResponse<Page<AppVO>> listMyAppVOByPage(@RequestBody AppQueryRequest appQueryRequest, HttpServletRequest request) {
        ThrowUtils.throwIf(appQueryRequest == null, ErrorCode.PARAMS_ERROR);
        User loginUser = userService.getLoginUser(request);
        // 限制每页最多 20 个
        long pageSize = normalizeUserPageSize(appQueryRequest.getPageSize());
        long pageNum = appQueryRequest.getPageNum();
        // 只查询当前用户的应用
        appQueryRequest.setUserId(loginUser.getId());
        QueryWrapper queryWrapper = appService.getQueryWrapper(appQueryRequest);
        Page<App> appPage = appService.page(Page.of(pageNum, pageSize), queryWrapper);
        // 数据封装
        Page<AppVO> appVOPage = new Page<>(pageNum, pageSize, appPage.getTotalRow());
        List<AppVO> appVOList = appService.getAppVOList(appPage.getRecords());
        appVOPage.setRecords(appVOList);
        return ResultUtils.success(appVOPage);
    }

    /**
     * 分页获取精选应用列表
     *
     * @param appQueryRequest 查询请求
     * @return 精选应用列表
     */
    @PostMapping("/good/list/page/vo")
    @Cacheable(
            value = "good_app_page", //KEY的前缀
            key = "T(com.rain.rainn0coding.utils.CacheKeyUtils).generateKey(#appQueryRequest)",
            condition = "#appQueryRequest.pageNum <= 10"
    )
    public BaseResponse<Page<AppVO>> listGoodAppVOByPage(@RequestBody AppQueryRequest appQueryRequest) {
        ThrowUtils.throwIf(appQueryRequest == null, ErrorCode.PARAMS_ERROR);
        // 限制每页最多 20 个
        long pageSize = normalizeUserPageSize(appQueryRequest.getPageSize());
        long pageNum = appQueryRequest.getPageNum();
        // 只查询精选的应用
        appQueryRequest.setPriority(AppConstant.GOOD_APP_PRIORITY);
        QueryWrapper queryWrapper = appService.getQueryWrapper(appQueryRequest);
        // 分页查询
        Page<App> appPage = appService.page(Page.of(pageNum, pageSize), queryWrapper);
        // 数据封装
        Page<AppVO> appVOPage = new Page<>(pageNum, pageSize, appPage.getTotalRow());
        List<AppVO> appVOList = appService.getAppVOList(appPage.getRecords());
        appVOPage.setRecords(appVOList);
        return ResultUtils.success(appVOPage);
    }

    /**
     * 管理员删除应用
     *
     * @param deleteRequest 删除请求
     * @return 删除结果
     */
    @PostMapping("/admin/delete")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<Boolean> deleteAppByAdmin(@RequestBody DeleteRequest deleteRequest) {
        if (deleteRequest == null || deleteRequest.getId() <= 0) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        long id = deleteRequest.getId();
        // 判断是否存在
        App oldApp = appService.getById(id);
        ThrowUtils.throwIf(oldApp == null, ErrorCode.NOT_FOUND_ERROR);
        boolean result = appService.removeById(id);
        return ResultUtils.success(result);
    }

    /**
     * 管理员更新应用
     *
     * @param appAdminUpdateRequest 更新请求
     * @return 更新结果
     */
    @PostMapping("/admin/update")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<Boolean> updateAppByAdmin(@RequestBody AppAdminUpdateRequest appAdminUpdateRequest) {
        if (appAdminUpdateRequest == null || appAdminUpdateRequest.getId() == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        long id = appAdminUpdateRequest.getId();
        // 判断是否存在
        App oldApp = appService.getById(id);
        ThrowUtils.throwIf(oldApp == null, ErrorCode.NOT_FOUND_ERROR);
        App app = new App();
        BeanUtil.copyProperties(appAdminUpdateRequest, app);
        // 设置编辑时间
        app.setEditTime(LocalDateTime.now());
        boolean result = appService.updateById(app);
        ThrowUtils.throwIf(!result, ErrorCode.OPERATION_ERROR);
        return ResultUtils.success(true);
    }

    /**
     * 管理员分页获取应用列表
     *
     * @param appQueryRequest 查询请求
     * @return 应用列表
     */
    @PostMapping("/admin/list/page/vo")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<Page<AppVO>> listAppVOByPageByAdmin(@RequestBody AppQueryRequest appQueryRequest) {
        ThrowUtils.throwIf(appQueryRequest == null, ErrorCode.PARAMS_ERROR);
        long pageNum = appQueryRequest.getPageNum();
        long pageSize = appQueryRequest.getPageSize();
        ThrowUtils.throwIf(pageSize <= 0 || pageSize > MAX_PAGE_SIZE, ErrorCode.PARAMS_ERROR, "每页最多查询 50 个应用");
        QueryWrapper queryWrapper = appService.getQueryWrapper(appQueryRequest);
        Page<App> appPage = appService.page(Page.of(pageNum, pageSize), queryWrapper);
        // 数据封装
        Page<AppVO> appVOPage = new Page<>(pageNum, pageSize, appPage.getTotalRow());
        List<AppVO> appVOList = appService.getAppVOList(appPage.getRecords());
        appVOPage.setRecords(appVOList);
        return ResultUtils.success(appVOPage);
    }

    /**
     * 管理员根据 id 获取应用详情
     *
     * @param id 应用 id
     * @return 应用详情
     */
    @GetMapping("/admin/get/vo")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<AppVO> getAppVOByIdByAdmin(long id) {
        ThrowUtils.throwIf(id <= 0, ErrorCode.PARAMS_ERROR);
        // 查询数据库
        App app = appService.getById(id);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR);
        // 获取封装类
        return ResultUtils.success(appService.getAppVO(app));
    }

    private long normalizeUserPageSize(long requestedPageSize) {
        ThrowUtils.throwIf(requestedPageSize <= 0, ErrorCode.PARAMS_ERROR, "分页参数错误");
        return Math.min(requestedPageSize, USER_PAGE_SIZE_LIMIT);
    }

    private Flux<ServerSentEvent<String>> duplicateSse(String status) {
        String type = "duplicate_completed".equals(status) ? "done" : "error";
        return Flux.just(
                ServerSentEvent.<String>builder()
                        .data(JSONUtil.toJsonStr(Map.of("d", JSONUtil.toJsonStr(Map.of(
                                "type", type,
                                "status", status
                        )))))
                        .build(),
                ServerSentEvent.<String>builder()
                        .event("done")
                        .data("")
                        .build()
        );
    }

    private Flux<ServerSentEvent<String>> failedReplaySse(IdempotencyRecord record) {
        int errorCode = record != null && record.getErrorCode() != null
                ? record.getErrorCode()
                : ErrorCode.SYSTEM_ERROR.getCode();
        String message = record != null && StrUtil.isNotBlank(record.getErrorMessage())
                ? record.getErrorMessage()
                : ErrorCode.SYSTEM_ERROR.getMessage();
        return Flux.just(
                ServerSentEvent.<String>builder()
                        .data(JSONUtil.toJsonStr(Map.of("d", JSONUtil.toJsonStr(Map.of(
                                "type", "error",
                                "status", "failed",
                                "code", errorCode,
                                "message", message
                        )))))
                        .build(),
                ServerSentEvent.<String>builder()
                        .event("done")
                        .data("")
                        .build()
        );
    }

    private <T> BaseResponse<T> replayResponse(IdempotencyDecision decision, Class<T> dataType) {
        if (decision.type() != IdempotencyDecision.Type.REPLAY_SUCCESS || decision.record() == null) {
            return null;
        }
        JSONObject responseJson = JSONUtil.parseObj(decision.record().getResultJson());
        T data = Convert.convert(dataType, responseJson.get("data"));
        return new BaseResponse<>(
                responseJson.getInt("code", ErrorCode.SUCCESS.getCode()),
                data,
                responseJson.getStr("message", "")
        );
    }

    private void replayFailed(IdempotencyDecision decision) {
        if (decision.type() != IdempotencyDecision.Type.REPLAY_FAILED) {
            return;
        }
        IdempotencyRecord record = decision.record();
        int errorCode = record != null && record.getErrorCode() != null
                ? record.getErrorCode()
                : ErrorCode.SYSTEM_ERROR.getCode();
        String message = record != null && StrUtil.isNotBlank(record.getErrorMessage())
                ? record.getErrorMessage()
                : ErrorCode.SYSTEM_ERROR.getMessage();
        throw new BusinessException(errorCode, message);
    }

    private void rejectActiveOrConflictingReplay(IdempotencyDecision decision) {
        if (decision.type() == IdempotencyDecision.Type.FINGERPRINT_MISMATCH) {
            throw new BusinessException(ErrorCode.REQUEST_REPLAY_CONFLICT);
        }
        if (decision.type() == IdempotencyDecision.Type.IN_PROGRESS) {
            throw new BusinessException(ErrorCode.REQUEST_IN_PROGRESS);
        }
    }

    private SseFailure detectSemanticFailure(String chunk) {
        JSONObject payload = parseSsePayload(chunk);
        if (payload == null) {
            return null;
        }
        String type = payload.getStr("type");
        String status = payload.getStr("status");
        if ("error".equals(type)) {
            return new SseFailure(errorCodeForStatus(status), semanticFailureMessage(payload, status));
        }
        if ("done".equals(type) && StrUtil.isNotBlank(status) && !"success".equals(status)) {
            if ("partial_success".equals(status) || "degraded_success".equals(status)) {
                return null;
            }
            return new SseFailure(errorCodeForStatus(status), semanticFailureMessage(payload, status));
        }
        return null;
    }

    private JSONObject parseSsePayload(String chunk) {
        if (StrUtil.isBlank(chunk)) {
            return null;
        }
        String json = chunk.trim();
        if (json.startsWith("data:")) {
            json = json.substring(5).trim();
        }
        if (!json.startsWith("{")) {
            return null;
        }
        try {
            return JSONUtil.parseObj(json);
        } catch (Exception e) {
            return null;
        }
    }

    private int errorCodeForStatus(String status) {
        if ("overloaded".equals(status)) {
            return ErrorCode.AI_GENERATION_OVERLOADED.getCode();
        }
        if ("partial_success".equals(status) || "degraded_success".equals(status)) {
            return ErrorCode.SUCCESS.getCode();
        }
        return ErrorCode.SYSTEM_ERROR.getCode();
    }

    private String semanticFailureMessage(JSONObject payload, String status) {
        if ("partial_success".equals(status) || "degraded_success".equals(status)) {
            return null;
        }
        String message = payload.getStr("message");
        if (StrUtil.isNotBlank(message)) {
            return message;
        }
        return StrUtil.isNotBlank(status) ? status : ErrorCode.SYSTEM_ERROR.getMessage();
    }

    private String systemErrorMessage(RuntimeException e) {
        return StrUtil.isNotBlank(e.getMessage()) ? e.getMessage() : ErrorCode.SYSTEM_ERROR.getMessage();
    }

    private record SseFailure(int errorCode, String message) {
    }

}
