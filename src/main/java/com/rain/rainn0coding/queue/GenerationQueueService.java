package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.ChatHistoryService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

@Service
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationQueueService {
    public record Snapshot(String taskId,String appId,String status,String errorMessage,String lastEventId,boolean retryAllowed) {}
    private final GenerationTaskStore store;
    private final GenerationQueueProperties config;
    private final AppService apps;
    private final ChatHistoryService history;
    private final GenerationWork work;
    public GenerationQueueService(GenerationTaskStore store,GenerationQueueProperties config,AppService apps,ChatHistoryService history,GenerationWork work) {
        this.store=store;this.config=config;this.apps=apps;this.history=history;this.work=work;
    }
    public Snapshot submit(Long appId,String message,String key,User user) {
        if(message==null||message.isBlank()||message.length()>config.getMaxPromptCharacters()||key==null||key.isBlank()||key.length()>128)
            throw new BusinessException(ErrorCode.PARAMS_ERROR,"消息或幂等键不合法");
        var app=ownedApp(appId,user);
        if(CodeGenTypeEnum.getEnumByValue(app.getCodeGenType())==null)throw new BusinessException(ErrorCode.PARAMS_ERROR);
        var task=store.submit(appId,user.getId(),message,app.getCodeGenType(),key,UUID.randomUUID().toString().replace("-",""),()->{
            if(!history.addChatMessage(appId,message,"user",user.getId()))throw new IllegalStateException("用户消息保存失败");
        });
        return snapshot(task);
    }
    public Snapshot get(String id,User user) {return snapshot(ownedTask(id,user));}
    public Snapshot latest(Long app,User user) {
        ownedApp(app,user);var task=store.latest(app,user.getId());return task==null?null:snapshot(task);
    }
    public boolean exists(String id) {return store.get(id)!=null;}
    public String resolveLegacyId(Long appId,String runId,User user) {
        ownedApp(appId,user);
        var direct=store.get(runId);
        if(direct!=null) {
            if(direct.appId()!=appId||direct.userId()!=user.getId())throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
            return runId;
        }
        var alias=store.byRequest(appId,user.getId(),runId);
        return alias==null?runId:alias.taskId();
    }
    public Snapshot pause(String id,User user) {
        var task=ownedTask(id,user);
        if(task.settled())return snapshot(task);
        if(store.pauseQueued(id))return snapshot(store.get(id));
        work.pause(task);
        store.markPausing(id);
        return snapshot(store.get(id));
    }
    public Snapshot resume(String id,User user) {
        var task=ownedTask(id,user);
        if(!List.of("PAUSED","INTERRUPTED").contains(task.status()))return snapshot(task);
        if(busyOrUnavailable(task.appId()))throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS,"原执行仍在结束中，请稍后继续");
        boolean checkpoint=store.shouldResume(id);
        if("INTERRUPTED".equals(task.status())) {
            // A task interrupted after claim may not have reached Python. Only an
            // authenticated 404 can establish that starting fresh is appropriate.
            try {
                var state=work.status(task.userId(),task.appId(),id);
                checkpoint=state.get("status")!=null;
            } catch(BusinessException e) {
                if(e.getCode()!=ErrorCode.NOT_FOUND_ERROR.getCode())throw e;
                checkpoint=false;
            }
        }
        return snapshot(store.resume(id,checkpoint));
    }
    public Snapshot importAndResume(Long appId,String runId,User user) {
        var app=ownedApp(appId,user);
        runId=resolveLegacyId(appId,runId,user);
        try {UUID.fromString(runId);}catch(Exception e){throw new BusinessException(ErrorCode.PARAMS_ERROR);}
        if(!exists(runId)) {
            var state=work.status(user.getId(),appId,runId);
            if(!List.of("paused","interrupted").contains(Objects.toString(state.get("status"),"")))
                throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS,"原任务尚不可继续");
            store.importLegacyPaused(runId,appId,user.getId(),app.getCodeGenType());
        } else if(ownedTask(runId,user).appId()!=appId) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR,"应用与任务不匹配");
        }
        return resume(runId,user);
    }
    private GenerationTaskStore.Task ownedTask(String id,User user) {
        var task=store.get(id);
        if(task==null)throw new BusinessException(ErrorCode.NOT_FOUND_ERROR);
        if(task.userId()!=user.getId())throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        ownedApp(task.appId(),user);return task;
    }
    private App ownedApp(Long id,User user) {
        if(id==null||id<=0)throw new BusinessException(ErrorCode.PARAMS_ERROR);
        var app=apps.getById(id);
        if(app==null)throw new BusinessException(ErrorCode.NOT_FOUND_ERROR);
        if(!user.getId().equals(app.getUserId()))throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        return app;
    }
    private boolean busyOrUnavailable(long app) {
        try{return work.busy(app);}catch(Exception e){return true;}
    }
    private Snapshot snapshot(GenerationTaskStore.Task task) {
        boolean retry=("FAILED".equals(task.status())||"INTERRUPTED".equals(task.status()))&&!busyOrUnavailable(task.appId());
        return new Snapshot(task.taskId(),String.valueOf(task.appId()),task.status(),task.errorMessage(),String.valueOf(task.lastEventId()),retry);
    }
    public void assertNoActiveTask(long app) {
        if(store.active(app)!=null)throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS,"请等待生成任务结束后再操作");
    }
    public Flux<ServerSentEvent<String>> events(String id,long after,User user) {
        var task=ownedTask(id,user);
        if(after<0||after>task.lastEventId())throw new BusinessException(ErrorCode.PARAMS_ERROR,"无效进度游标");
        return Flux.defer(()->{
            var cursor=new AtomicLong(after);
            return Flux.interval(Duration.ZERO,Duration.ofMillis(750)).onBackpressureDrop()
                    .concatMap(tick->Mono.fromCallable(()->poll(id,cursor,tick)).subscribeOn(Schedulers.boundedElastic()),1)
                    .takeUntil(Batch::terminal).concatMapIterable(Batch::events);
        });
    }
    private record Batch(List<ServerSentEvent<String>> events,boolean terminal) {}
    private Batch poll(String id,AtomicLong cursor,long tick) {
        var events=store.events(id,cursor.get());
        var out=new ArrayList<ServerSentEvent<String>>();
        for(var event:events) {
            out.add(ServerSentEvent.<String>builder().id(String.valueOf(event.id())).data(event.data()).build());cursor.set(event.id());
        }
        var task=store.get(id);
        if(task==null)throw new IllegalStateException("任务不存在");
        boolean terminal=task.settled()&&(cursor.get()>=task.lastEventId()||events.isEmpty());
        if(terminal&&events.isEmpty()) {
            String status="SUCCEEDED".equals(task.status())?"success":task.status().toLowerCase();
            out.add(ServerSentEvent.<String>builder().id(String.valueOf(task.lastEventId()))
                    .data(JSONUtil.toJsonStr(Map.of("type","done","status",status,"message",Objects.toString(task.errorMessage(),"")))).build());
        } else if(out.isEmpty()&&tick%20==0)out.add(ServerSentEvent.<String>builder().comment("keepalive").build());
        return new Batch(out,terminal);
    }
}
