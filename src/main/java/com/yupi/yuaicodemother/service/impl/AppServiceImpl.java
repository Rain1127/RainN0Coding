package com.yupi.yuaicodemother.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.RandomUtil;
import cn.hutool.core.util.StrUtil;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.yupi.yuaicodemother.ai.AiCodeGenTypeRoutingService;
import com.yupi.yuaicodemother.ai.AiCodeGenTypeRoutingServiceFactory;
import com.yupi.yuaicodemother.constant.AppConstant;
import com.yupi.yuaicodemother.core.AiCodeGeneratorFacade;
import com.yupi.yuaicodemother.core.builder.VueProjectBuilder;
import com.yupi.yuaicodemother.core.handler.StreamHandlerExecutor;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import com.yupi.yuaicodemother.mapper.AppMapper;
import com.yupi.yuaicodemother.model.dto.app.AppAddRequest;
import com.yupi.yuaicodemother.model.dto.app.AppQueryRequest;
import com.yupi.yuaicodemother.model.entity.App;
import com.yupi.yuaicodemother.model.enums.ChatHistoryMessageTypeEnum;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import com.yupi.yuaicodemother.model.vo.AppVO;
import com.yupi.yuaicodemother.model.vo.UserVO;
import com.yupi.yuaicodemother.service.AppService;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.service.ChatHistoryService;
import com.yupi.yuaicodemother.service.ScreenshotService;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.io.File;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 应用 服务层实现。
 *
 * @author <a>Rain</a>
 */
@Service
@Slf4j
public class AppServiceImpl extends ServiceImpl<AppMapper,App>  implements AppService{

    @Resource
    private UserService userService;

    @Resource
    private ChatHistoryService chatHistoryService;

    @Resource
    private StreamHandlerExecutor streamHandlerExecutor;

    @Resource
    private AiCodeGeneratorFacade aiCodeGeneratorFacade;

    @Resource
    private VueProjectBuilder vueProjectBuilder;

    @Resource
    private ScreenshotService screenshotService;

    @Resource
    private AiCodeGenTypeRoutingServiceFactory aiCodeGenTypeRoutingServiceFactory;

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
        //1.参数校验
        ThrowUtils.throwIf(appId == null || appId<=0 , ErrorCode.PARAMS_ERROR, "应用id错误");
        ThrowUtils.throwIf(StrUtil.isBlank(message), ErrorCode.PARAMS_ERROR, "提示词消息不能为空");
        //2.查询应用
        App app = this.getById(appId);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR, "应用不存在");
        //3.权限校验 只有本人可以和自己的应用对话
        if (!app.getUserId().equals(loginUser.getId())){
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR, "没有权限对话该应用");
        }
        //4.获取应用代码生成类型（纯HTML还是三件套？）
        String codeGenType = app.getCodeGenType();
        CodeGenTypeEnum codeGenTypeEnum = CodeGenTypeEnum.getEnumByValue(codeGenType);
        ThrowUtils.throwIf(codeGenTypeEnum == null, ErrorCode.PARAMS_ERROR, "应用代码生成类型错误");
        //5.在调用AI前，先保存用户消息到数据库中
        chatHistoryService.addChatMessage(appId, message, ChatHistoryMessageTypeEnum.USER.getValue(), loginUser.getId());
        //6.调用AI生成代码
        Flux<String> codeStream = aiCodeGeneratorFacade.generateAndSaveCodeStream(message, codeGenTypeEnum, appId);
        //7.收集AI流式返回的代码，并且在完成对话后保存记录到数据库对话历史表中
        return streamHandlerExecutor.doExecute(codeStream, chatHistoryService, appId, loginUser, codeGenTypeEnum);
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
        // 使用 AI 智能选择代码生成类型(多例模式)
        AiCodeGenTypeRoutingService aiCodeGenTypeRoutingService = aiCodeGenTypeRoutingServiceFactory.createAiCodeGenTypeRoutingService();
        CodeGenTypeEnum selectedCodeGenType = aiCodeGenTypeRoutingService.routeCodeGenType(initPrompt);
        app.setCodeGenType(selectedCodeGenType.getValue());
        // 插入数据库
        boolean result = this.save(app);
        ThrowUtils.throwIf(!result, ErrorCode.OPERATION_ERROR);
        log.info("应用创建成功，ID: {}, 类型: {}", app.getId(), selectedCodeGenType.getValue());
        return app.getId();
    }


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
        String appDeployUrl = String.format("%s/%s", AppConstant.CODE_DEPLOY_HOST, deployKey);
        //11.异步执行截图并且更新封面
        generateAppScreenshotAsync(appId,appDeployUrl);
        return appDeployUrl;
    }

    /**
     * 异步生成应用截图并更新应用封面
     * @param appId 应用id
     * @param appDeployUrl 应用部署URL
     */
    @Override
    public void generateAppScreenshotAsync(Long appId, String appDeployUrl){
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
            AppVO appVO = getAppVO(app);
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
        return QueryWrapper.create()
                .eq("id", id)
                .like("appName", appName)
                .like("cover", cover)
                .like("initPrompt", initPrompt)
                .eq("codeGenType", codeGenType)
                .eq("deployKey", deployKey)
                .eq("priority", priority)
                .eq("userId", userId)
                .orderBy(sortField, "ascend".equals(sortOrder));
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
