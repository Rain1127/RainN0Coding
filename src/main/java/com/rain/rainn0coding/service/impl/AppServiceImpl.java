package com.rain.rainn0coding.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.RandomUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.rain.rainn0coding.constant.AppConstant;
import com.rain.rainn0coding.concurrency.AiGenerationPermitService;
import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.core.builder.VueProjectBuilder;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.ThrowUtils;
import com.rain.rainn0coding.mapper.AppMapper;
import com.rain.rainn0coding.model.dto.app.AppAddRequest;
import com.rain.rainn0coding.model.dto.app.AppQueryRequest;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.enums.ChatHistoryMessageTypeEnum;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import com.rain.rainn0coding.model.vo.AppVO;
import com.rain.rainn0coding.model.vo.UserVO;
import com.rain.rainn0coding.monitor.MonitorContext;
import com.rain.rainn0coding.monitor.MonitorContextHolder;
import com.rain.rainn0coding.monitor.TraceIdResolver;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.ChatHistoryService;
import com.rain.rainn0coding.service.ScreenshotService;
import com.rain.rainn0coding.service.UserService;
import com.rain.rainn0coding.utils.SqlSafetyUtils;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RLock;
import org.redisson.api.RFuture;
import org.redisson.api.RedissonClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.io.File;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

/**
 * 应用 服务层实现。
 *
 * @author <a>Rain</a>
 */
@Service
@Slf4j
public class AppServiceImpl extends ServiceImpl<AppMapper,App>  implements AppService{

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
            "id", "appName", "codeGenType", "priority", "createTime", "editTime", "deployedTime"
    );
    private static final CodeGenTypeEnum DEFAULT_CODE_GEN_TYPE = CodeGenTypeEnum.VUE_PROJECT;

    @Value("${app.deploy-host:http://localhost:8123/api/static}")
    private String codeDeployHost = "http://localhost:8123/api/static";

    @Resource
    private UserService userService;

    @Resource
    private ChatHistoryService chatHistoryService;

    @Resource
    private AiCodeGeneratorFacade aiCodeGeneratorFacade;

    @Resource
    private VueProjectBuilder vueProjectBuilder;

    @Resource
    private ScreenshotService screenshotService;

    @Resource
    private PythonAiClient pythonAiClient;

    @Resource
    private RedissonClient redissonClient;

    @Resource
    private TraceIdResolver traceIdResolver;

    @Resource
    private AiGenerationPermitService aiGenerationPermitService;

    /**
     * 应用对话：根据应用id和用户提示词生成代码。
     *
     * @param appId    应用id
     * @param message  用户提示词
     * @param loginUser 当前登录用户
     * @return 生成的代码流
     */
    @Override
    public Flux<String> chatToGenCode(Long appId, String message, User loginUser) {
        return chatToGenCode(appId, message, loginUser, null, null);
    }

    @Override
    public Flux<String> chatToGenCode(Long appId, String message, User loginUser, String requestId, String idempotencyKey) {
        //1.参数校验
        ThrowUtils.throwIf(appId == null || appId<=0 , ErrorCode.PARAMS_ERROR, "应用id错误");
        ThrowUtils.throwIf(StrUtil.isBlank(message), ErrorCode.PARAMS_ERROR, "提示词消息不能为空");
        return Flux.defer(() -> doChatToGenCode(appId, message, loginUser, requestId, idempotencyKey));
    }

    private Flux<String> doChatToGenCode(Long appId, String message, User loginUser, String requestId, String idempotencyKey) {
        //2.获取分布式锁，防止同应用并发对话
        String lockKey = "ai:chat:lock:" + appId + ":" + loginUser.getId();
        RLock lock = redissonClient.getLock(lockKey);
        boolean locked = false;
        long lockThreadId = -1L;
        try {
            locked = lock.tryLock(0, TimeUnit.SECONDS);
            if (locked) {
                lockThreadId = Thread.currentThread().threadId();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.SYSTEM_ERROR, "系统繁忙，请稍后重试");
        }
        if (!locked) {
            throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS);
        }
        final long acquiredLockThreadId = lockThreadId;
        AiGenerationPermitService.PermitHandle permit = null;
        try {
            //3.查询应用
            App app = this.getById(appId);
            ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR, "应用不存在");
            //4.权限校验 只有本人可以和自己的应用对话
            if (!app.getUserId().equals(loginUser.getId())){
                throw new BusinessException(ErrorCode.NO_AUTH_ERROR, "没有权限对话该应用");
            }
            //5.获取应用代码生成类型（纯HTML还是三件套？）
            String codeGenType = app.getCodeGenType();
            CodeGenTypeEnum codeGenTypeEnum = CodeGenTypeEnum.getEnumByValue(codeGenType);
            ThrowUtils.throwIf(codeGenTypeEnum == null, ErrorCode.PARAMS_ERROR, "应用代码生成类型错误");
            //6.在调用AI前，先保存用户消息到数据库中
            chatHistoryService.addChatMessage(appId, message, ChatHistoryMessageTypeEnum.USER.getValue(), loginUser.getId());
            //7.设置监控上下文（含全链路 traceId）
            String traceId = traceIdResolver.resolveCurrentTraceId();
            log.info("全链路追踪 traceId: {}", traceId);
            MonitorContext monitorContext = MonitorContext.builder()
                    .userId(loginUser.getId().toString())
                    .appId(appId.toString())
                    .traceId(traceId)
                    .build();
            MonitorContextHolder.setContext(monitorContext);
            //8.调用 Python AI Agent 生成代码（SSE 流式透传）
            permit = aiGenerationPermitService.tryAcquire();
            if (!permit.acquired()) {
                chatHistoryService.addChatMessage(appId,
                        "[Python Agent] 代码生成失败: AI 生成服务繁忙",
                        ChatHistoryMessageTypeEnum.AI.getValue(),
                        loginUser.getId());
                return Flux.just(
                                "{\"type\":\"error\",\"status\":\"overloaded\",\"message\":\"AI generation capacity is full. Please retry later.\"}",
                                "{\"type\":\"done\",\"status\":\"overloaded\"}"
                        )
                        .doFinally(signalType -> {
                            releaseLock(lock, acquiredLockThreadId);
                            MonitorContextHolder.clearContext();
                        });
            }
            AiGenerationPermitService.PermitHandle acquiredPermit = permit;
            Flux<String> codeStream = aiCodeGeneratorFacade.generateAndSaveCodeStream(
                    message, codeGenTypeEnum, appId, loginUser.getId(), loginUser.getUserRole(), requestId, idempotencyKey);
            //9.流完成后保存 AI 响应到对话历史
            AtomicReference<String> semanticFailure = new AtomicReference<>();
            return codeStream
                    .doOnNext(chunk -> {
                        String failure = semanticFailureMessage(chunk);
                        if (failure != null) {
                            semanticFailure.compareAndSet(null, failure);
                        }
                    })
                    .doOnComplete(() -> {
                        String failure = semanticFailure.get();
                        if (failure != null) {
                            chatHistoryService.addChatMessage(appId,
                                    "[Python Agent] 代码生成失败: " + failure,
                                    ChatHistoryMessageTypeEnum.AI.getValue(),
                                    loginUser.getId());
                            return;
                        }
                        chatHistoryService.addChatMessage(appId,
                                "[Python Agent] 代码生成完成",
                                ChatHistoryMessageTypeEnum.AI.getValue(),
                                loginUser.getId());
                    })
                    .doFinally(signalType -> {
                        aiGenerationPermitService.release(acquiredPermit);
                        //流结束时释放锁
                        releaseLock(lock, acquiredLockThreadId);
                        //流结束时清理ThreadLocal中的监控上下文
                        MonitorContextHolder.clearContext();
                    });
        } catch (Exception e) {
            //异常时释放锁
            aiGenerationPermitService.release(permit);
            releaseLock(lock, lockThreadId);
            MonitorContextHolder.clearContext();
            throw e;
        }
    }

    private String semanticFailureMessage(String chunk) {
        JSONObject payload = parseSsePayload(chunk);
        if (payload == null) {
            return null;
        }
        String type = payload.getStr("type");
        String status = payload.getStr("status");
        if ("error".equals(type)) {
            return StrUtil.blankToDefault(payload.getStr("message"), StrUtil.blankToDefault(status, "error"));
        }
        if ("done".equals(type) && StrUtil.isNotBlank(status)) {
            if ("partial_success".equals(status) || "degraded_success".equals(status)) {
                return null;
            }
            if (!"success".equals(status)) {
                return status;
            }
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


    private void releaseLock(RLock lock, long lockThreadId) {
        if (lock == null || lockThreadId < 0) {
            return;
        }
        try {
            RFuture<Void> unlockFuture = lock.unlockAsync(lockThreadId);
            if (unlockFuture != null) {
                unlockFuture.onComplete((ignored, throwable) -> {
                    if (throwable != null) {
                        log.warn("Release AI chat lock failed for thread {}: {}", lockThreadId, throwable.getMessage());
                    }
                });
            }
        } catch (Exception e) {
            log.warn("Release AI chat lock failed for thread {}: {}", lockThreadId, e.getMessage());
        }
    }


    @Override
    public Long createApp(AppAddRequest appAddRequest, User loginUser) {
        // 参数校验
        String initPrompt = appAddRequest.getInitPrompt();
        ThrowUtils.throwIf(StrUtil.isBlank(initPrompt), ErrorCode.PARAMS_ERROR, "初始化 prompt 不能为空");
        // 构造入库对象
        App app = new App();
        BeanUtil.copyProperties(appAddRequest, app);
        app.setUserId(loginUser.getId());
        // 应用名称暂时为 initPrompt 前 12 位
        app.setAppName(initPrompt.substring(0, Math.min(initPrompt.length(), 12)));
        // 代码生成类型路由已迁到 Python agent，Java 侧仅接收结果并兜底
        CodeGenTypeEnum selectedCodeGenType = resolveCodeGenType(initPrompt);
        app.setCodeGenType(selectedCodeGenType.getValue());
        // 插入数据库
        boolean result = this.save(app);
        ThrowUtils.throwIf(!result, ErrorCode.OPERATION_ERROR);
        log.info("应用创建成功，ID: {}, 类型: {}", app.getId(), selectedCodeGenType.getValue());
        return app.getId();
    }


    /**
     * 部署APP
     *
     * @param appId     应用id
     * @param loginUser 登录用户
     * @return
     */
    @Override
    public String deployApp(Long appId, User loginUser) {
        //1.参数校验
        ThrowUtils.throwIf(appId == null || appId<=0 , ErrorCode.PARAMS_ERROR, "应用id错误");
        ThrowUtils.throwIf(loginUser == null, ErrorCode.PARAMS_ERROR, "登录用户不能为空");
        //2.查询应用信息
        App app = this.getById(appId);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR, "应用不存在");
        //3.权限校验 只有本人可以部署自己的应用
        if (!app.getUserId().equals(loginUser.getId())){
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR, "没有权限部署该应用");
        }
        //4.检查是否已存在deployKey
        //如果没有，则生成六位deployKey(字母+数字)
        String deployKey = app.getDeployKey();
        if (StrUtil.isBlank(deployKey)){
            deployKey = RandomUtil.randomNumbers(6);
        }
        //5.获取代码生成类型，获取原始代码生成路径（应用访问目录）
        String codeGenType = app.getCodeGenType();
        String sourceDirName = codeGenType+"_"+appId;
        String sourceDirPath = AppConstant.CODE_OUTPUT_ROOT_DIR+ File.separator +sourceDirName;
        //6.检查路径是否存在
        File sourceDir = new File(sourceDirPath);
        if(!sourceDir.exists() || !sourceDir.isDirectory()){
            throw new BusinessException(ErrorCode.NOT_FOUND_ERROR, "应用代码目录不存在");
        }
        //7. VUE项目特殊处理
        CodeGenTypeEnum codeGenTypeEnum = CodeGenTypeEnum.getEnumByValue(codeGenType);
        if(codeGenTypeEnum == CodeGenTypeEnum.VUE_PROJECT){
            //7.1 构建Vue项目
            boolean buildSuccess = vueProjectBuilder.buildProject(sourceDirPath);
            ThrowUtils.throwIf(!buildSuccess, ErrorCode.OPERATION_ERROR, "Vue项目构建失败");
            //7.2 检查dist目录是否存在
            File distDir = new File(sourceDirPath, "dist");
            ThrowUtils.throwIf(!distDir.exists() || !distDir.isDirectory(), ErrorCode.OPERATION_ERROR, "Vue项目构建完成但dist目录不存在");
            //7.3 复制dist目录到部署目录
            sourceDir = distDir;
        }
        sourceDir = resolveStaticDeploySource(sourceDir, codeGenTypeEnum);
        //8.复制文件到部署目录
        String deployDirPath = AppConstant.CODE_DEPLOY_ROOT_DIR+ File.separator +deployKey;
        try{
            FileUtil.copyContent(sourceDir,new File(deployDirPath),true);
        }catch (Exception e){
            throw new BusinessException(ErrorCode.SYSTEM_ERROR, "部署应用失败");
        }
        //9.更新数据库
        App updateApp = new App();
        updateApp.setId(appId);
        updateApp.setDeployKey(deployKey);
        updateApp.setDeployedTime(LocalDateTime.now());
        boolean updateResult = this.updateById(updateApp);
        ThrowUtils.throwIf(!updateResult, ErrorCode.OPERATION_ERROR, "更新应用部署信息失败");
        //10.返回可访问的URL地址
        String appDeployUrl = buildDeployUrl(deployKey);
        //11.异步执行截图并且更新封面
        generateAppScreenshotAsync(appId,appDeployUrl);
        return appDeployUrl;
    }

    String buildDeployUrl(String deployKey) {
        return String.format("%s/%s/", StrUtil.removeSuffix(codeDeployHost, "/"), deployKey);
    }

    File resolveStaticDeploySource(File sourceDir, CodeGenTypeEnum codeGenType) {
        if (codeGenType == CodeGenTypeEnum.HTML || codeGenType == CodeGenTypeEnum.MULTI_FILE) {
            File nestedSourceDir = new File(sourceDir, "src");
            File nestedIndex = new File(nestedSourceDir, "index.html");
            if (!new File(sourceDir, "index.html").isFile() && nestedIndex.isFile()) {
                return nestedSourceDir;
            }
        }
        return sourceDir;
    }

    private CodeGenTypeEnum resolveCodeGenType(String prompt) {
        try {
            String rawCodeGenType = pythonAiClient.routeCodeGenType(prompt);
            CodeGenTypeEnum resolved = normalizeCodeGenType(rawCodeGenType);
            if (resolved != null) {
                return resolved;
            }
            log.warn("Python agent returned unsupported codeGenType: {}, fallback to {}",
                    rawCodeGenType, DEFAULT_CODE_GEN_TYPE.getValue());
        } catch (Exception e) {
            log.warn("Python agent routeCodeGenType failed, fallback to {}: {}",
                    DEFAULT_CODE_GEN_TYPE.getValue(), e.getMessage());
        }
        return DEFAULT_CODE_GEN_TYPE;
    }

    private CodeGenTypeEnum normalizeCodeGenType(String rawCodeGenType) {
        if (StrUtil.isBlank(rawCodeGenType)) {
            return null;
        }
        String normalized = rawCodeGenType.trim()
                .toLowerCase(Locale.ROOT)
                .replace('-', '_')
                .replace(' ', '_');
        return CodeGenTypeEnum.getEnumByValue(normalized);
    }

    /**
     * 异步生成应用截图并更新应用封面
     * @param appId 应用id
     * @param appDeployUrl 应用部署URL
     */
    private void generateAppScreenshotAsync(Long appId, String appDeployUrl){
        //使用虚拟线程异步执行截图
        Thread.startVirtualThread(() ->{
            String screenshotUrl = screenshotService.generateAndUploadScreenshot(appDeployUrl);
            //更新数据库封面字段
            App app = new App();
            app.setId(appId);
            app.setCover(screenshotUrl);
            boolean updated = this.updateById(app);
            ThrowUtils.throwIf(!updated, ErrorCode.OPERATION_ERROR, "更新应用封面失败");
        });
    }

    /**
     * 将应用实体转换为应用视图对象。
     *
     * @param app 应用实体
     * @return 应用视图对象
     */
    @Override
    public AppVO getAppVO(App app) {
        if (app == null) {
            return null;
        }
        AppVO appVO = new AppVO();
        BeanUtil.copyProperties(app, appVO);
        // 关联查询用户信息
        Long userId = app.getUserId();
        if (userId != null) {
            User user = userService.getById(userId);
            UserVO userVO = userService.getUserVO(user);
            appVO.setUser(userVO);
        }
        return appVO;
    }

    /**
     * 批量获取应用视图对象列表。
     *
     * @param appList 应用实体列表
     * @return 应用视图对象列表
     */
    @Override
    public List<AppVO> getAppVOList(List<App> appList) {
        if (CollUtil.isEmpty(appList)) {
            return new ArrayList<>();
        }
        // 批量获取用户信息，避免 N+1 查询问题
        Set<Long> userIds = appList.stream()
                .map(App::getUserId)
                .collect(Collectors.toSet());
        // 批量获取用户视图对象
        Map<Long, UserVO> userVOMap = userService.listByIds(userIds).stream()
                .collect(Collectors.toMap(User::getId, userService::getUserVO));

        return appList.stream().map(app -> {
            AppVO appVO = new AppVO();
            BeanUtil.copyProperties(app, appVO);
            UserVO userVO = userVOMap.get(app.getUserId());
            appVO.setUser(userVO);
            return appVO;
        }).collect(Collectors.toList());
    }

    /**
     * 构造应用分页查询条件。
     *
     * @param appQueryRequest 应用查询请求参数
     * @return 查询条件包装器
     */
    @Override
    public QueryWrapper getQueryWrapper(AppQueryRequest appQueryRequest) {
        if (appQueryRequest == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "请求参数为空");
        }
        Long id = appQueryRequest.getId();
        String appName = appQueryRequest.getAppName();
        String cover = appQueryRequest.getCover();
        String initPrompt = appQueryRequest.getInitPrompt();
        String codeGenType = appQueryRequest.getCodeGenType();
        String deployKey = appQueryRequest.getDeployKey();
        Integer priority = appQueryRequest.getPriority();
        Long userId = appQueryRequest.getUserId();
        String sortField = appQueryRequest.getSortField();
        String sortOrder = appQueryRequest.getSortOrder();
        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq("id", id)
                .like("appName", appName)
                .like("cover", cover)
                .like("initPrompt", initPrompt)
                .eq("codeGenType", codeGenType)
                .eq("deployKey", deployKey)
                .eq("priority", priority)
                .eq("userId", userId);
        String safeSortField = SqlSafetyUtils.safeSortField(sortField, ALLOWED_SORT_FIELDS);
        if (safeSortField != null) {
            queryWrapper.orderBy(safeSortField, "ascend".equals(sortOrder));
        }
        return queryWrapper;
    }

    /**
     * 根据应用ID删除应用,并关联删除对话历史
     *
     * @param id 应用ID
     * @return 是否删除成功
     */
    @Override
    public boolean removeById(Serializable id) {
        if (id == null) {
            return false;
        }
        Long appId = Long.valueOf(id.toString());
        if (appId<=0){
            return false;
        }
        //先删除应用关联的对话历史
        try {
            chatHistoryService.deleteByAppId(appId);
        } catch (Exception e) {
            log.error("删除应用对话历史失败,{}",e.getMessage());
        }
        //删除应用,注意，这里不能用this。因为这里本来就是重写了类方法。
        return super.removeById(appId);
    }
}
