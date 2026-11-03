package com.rain.rainn0coding.controller;

import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.core.ArtifactVersionService;
import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/app/{appId}/versions")
public class ArtifactVersionController {
    private final ArtifactVersionService versions;
    private final UserService users;
    private final AiCodeGeneratorFacade facade;
    private final PythonAiClient python;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.rain.rainn0coding.queue.GenerationQueueService queue;
    public ArtifactVersionController(ArtifactVersionService versions, UserService users, AiCodeGeneratorFacade facade, PythonAiClient python) {
        this.versions=versions;this.users=users;this.facade=facade;this.python=python;
    }
    @GetMapping
    public BaseResponse<List<ArtifactVersionService.Version>> list(@PathVariable long appId,HttpServletRequest request) {
        return ResultUtils.success(versions.list(appId,users.getLoginUser(request).getId()));
    }
    @PostMapping("/{versionId}/rollback")
    public BaseResponse<Boolean> rollback(@PathVariable long appId,@PathVariable long versionId,HttpServletRequest request) {
        long userId=users.getLoginUser(request).getId();
        versions.list(appId,userId);
        if(queue!=null)queue.assertNoActiveTask(appId);
        if(facade.isFinalizing(appId)||python.isExecutionBusy(appId))throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS);
        versions.rollback(appId,versionId,userId);
        return ResultUtils.success(true);
    }
}
