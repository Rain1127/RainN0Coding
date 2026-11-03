package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import com.rain.rainn0coding.monitor.MonitorContext;
import com.rain.rainn0coding.monitor.MonitorContextHolder;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.ChatHistoryService;
import com.rain.rainn0coding.service.UserService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationWork {
    private final AiCodeGeneratorFacade facade;
    private final PythonAiClient python;
    private final AppService apps;
    private final UserService users;
    private final ChatHistoryService history;
    private final GenerationTaskStore store;
    public GenerationWork(AiCodeGeneratorFacade facade,PythonAiClient python,AppService apps,UserService users,ChatHistoryService history,GenerationTaskStore store) {
        this.facade=facade;this.python=python;this.apps=apps;this.users=users;this.history=history;this.store=store;
    }
    public boolean busy(long appId) {
        try {return facade.isFinalizing(appId)||python.isExecutionBusy(appId);}
        catch(RuntimeException unavailable) {throw new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE);}
    }
    public Flux<String> stream(GenerationTaskStore.Task task) {
        var user=users.getById(task.userId());
        var app=apps.getById(task.appId());
        if(user==null||app==null||!Long.valueOf(task.userId()).equals(app.getUserId()))
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR,"应用或用户已失效");
        if(store.finalized(task.taskId()))return Flux.just("{\"type\":\"done\",\"status\":\"success\"}");
        MonitorContextHolder.setContext(MonitorContext.builder().appId(String.valueOf(task.appId()))
                .userId(String.valueOf(task.userId())).traceId(task.traceId()).build());
        var succeeded=new java.util.concurrent.atomic.AtomicBoolean();
        var failed=new java.util.concurrent.atomic.AtomicBoolean();
        try {
            return facade.generateAndSaveCodeStream(task.prompt(),CodeGenTypeEnum.getEnumByValue(task.codeGenType()),
                    task.appId(),task.userId(),user.getUserRole(),task.taskId(),task.taskId(),store.shouldResume(task.taskId()),true,
                    ()->store.owns(task.taskId(),task.ownerId()))
                    .doOnNext(raw->{
                        var json=cn.hutool.json.JSONUtil.parseObj(raw.startsWith("data:")?raw.substring(5).trim():raw);
                        if("error".equals(json.getStr("type")))failed.set(true);
                        if("done".equals(json.getStr("type")))succeeded.set(java.util.Set.of("success","degraded_success").contains(json.getStr("status","")));
                    })
                    .doOnComplete(()->{if(succeeded.get()&&!failed.get())store.markFinalized(task.taskId(),task.ownerId());});
        } finally {MonitorContextHolder.clearContext();}
    }
    public java.util.Map<String,Object> pause(GenerationTaskStore.Task task) {
        return python.pauseGeneration(String.valueOf(task.userId()),String.valueOf(task.appId()),task.taskId());
    }
    public java.util.Map<String,Object> status(long userId,long appId,String id) {
        return python.generationStatus(String.valueOf(userId),String.valueOf(appId),id);
    }
    public void completeHistory(GenerationTaskStore.Task task,String status,String message) {
        String text="SUCCEEDED".equals(status)?"[Python Agent] 代码生成完成":"[Python Agent] 代码生成失败: "+message;
        if(!history.addChatMessage(task.appId(),text,"ai",task.userId()))throw new IllegalStateException("聊天记录保存失败");
    }
}
