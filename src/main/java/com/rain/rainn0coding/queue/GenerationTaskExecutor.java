package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.GenerationLeaseLostException;
import org.springframework.dao.DataAccessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;
import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Only Kafka consumers execute work. Browser subscriptions never call this class. */
@Component
@Slf4j
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationTaskExecutor {
    private static final Set<String> SUCCESS=Set.of("success","degraded_success");
    private final GenerationTaskStore store;
    private final GenerationWork work;
    private final GenerationQueueProperties config;
    private final Set<String> active=java.util.concurrent.ConcurrentHashMap.newKeySet();
    public GenerationTaskExecutor(GenerationTaskStore store,GenerationWork work,GenerationQueueProperties config) {
        this.store=store;this.work=work;this.config=config;
    }
    public void execute(String id) {
        if(!active.add(id))return;
        try {executeTask(id);} finally {active.remove(id);}
    }
    public boolean isExecuting(String id) {return active.contains(id);}

    private void executeTask(String id) {
        var task=store.get(id);
        if(task==null||task.settled())return;
        // Redelivery never revokes a live execution. The recovery coordinator checks lease + Python ownership.
        if(!"QUEUED".equals(task.status()))return;
        if(work.busy(task.appId())) {
            store.delayQueued(id,false,()->{});return;
        }
        String owner=UUID.randomUUID().toString();
        if(!store.claim(id,owner)) {
            if(store.paused())throw new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE);
            return;
        }
        var owned=new GenerationTaskStore.Task(task.taskId(),task.appId(),task.userId(),task.prompt(),task.codeGenType(),
                task.idempotencyKey(),task.traceId(),"RUNNING",task.errorMessage(),task.lastEventId(),task.createdAt(),owner);
        var successfulDone=new AtomicBoolean(false);
        var pausedDone=new AtomicBoolean(false);
        var failure=new AtomicReference<String>();
        String status="SUCCEEDED";
        String message=null;
        try {
            var heartbeat=Flux.interval(Duration.ofSeconds(config.getHeartbeatSeconds()))
                    .publishOn(Schedulers.boundedElastic(),1).doOnNext(tick->store.heartbeat(id,owner)).then();
            work.stream(owned).publishOn(Schedulers.boundedElastic(),1)
                    .doOnNext(raw -> {
                        String json=raw.startsWith("data:")?raw.substring(5).trim():raw.trim();
                        if(!JSONUtil.isTypeJSONObject(json))throw new IllegalStateException("生成事件格式错误");
                        var event=JSONUtil.parseObj(json);
                        String type=event.getStr("type");
                        if("done".equals(type)) {
                            if("paused".equals(event.getStr("status"))) {pausedDone.set(true);return;}
                            successfulDone.set(SUCCESS.contains(event.getStr("status","")));
                            if(!successfulDone.get())failure.compareAndSet(null,event.getStr("message","生成未成功完成"));
                            return; // The durable terminal event follows save/build and history commit.
                        }
                        if("error".equals(type))failure.compareAndSet(null,event.getStr("message","生成失败"));
                        if("code_file".equals(type)) {
                            String content=event.getStr("content");
                            if(content!=null&&!event.containsKey("size"))event.set("size",content.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
                            event.remove("content");event.remove("source");
                            json=event.toString();
                        }
                        store.appendOwned(id,owner,json);
                    })
                    .takeUntilOther(heartbeat)
                    .takeUntilOther(Mono.delay(Duration.ofMinutes(config.getTaskTimeoutMinutes()))
                            .flatMap(ignored->Mono.error(new IllegalStateException("任务超过最长执行时间"))))
                    .blockLast();
            if(pausedDone.get()&&failure.get()==null) {store.pauseOwned(id,owner);return;}
            if(!successfulDone.get()||failure.get()!=null) {
                status="FAILED"; message=failure.get()!=null?failure.get():"生成连接结束但没有成功结果";
            }
        } catch(Exception e) {
            if(e instanceof GenerationLeaseLostException)return;
            var kind=GenerationFailurePolicy.classify(e);
            log.warn("Generation task {} execution failed ({})",id,kind);
            // Storage failures propagate without ack. Do not misclassify a failed event write as an Agent failure.
            if(e instanceof DataAccessException)throw e;
            boolean busy;
            try {busy=work.busy(task.appId());}
            catch(Exception unavailable) {busy=true;kind=GenerationFailurePolicy.Kind.INFRASTRUCTURE;}
            if(busy||kind!=GenerationFailurePolicy.Kind.TERMINAL) {
                store.requestRecovery(id,owner,kind);
                if(kind==GenerationFailurePolicy.Kind.INFRASTRUCTURE)
                    throw new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE);
                return;
            }
            status="FAILED";message="生成执行失败，请重试或联系管理员";
        }
        // Persistence exceptions propagate to Kafka; a redelivery never reruns a claimed task.
        String terminalStatus=status,terminalMessage=message;
        store.finishOwned(id,owner,status,message,()->work.completeHistory(owned,terminalStatus,terminalMessage));
    }
    public void expireQueued() {
        for(var task:store.expired()) store.finishQueued(task.taskId(),"排队超时，请重新提交",
                ()->work.completeHistory(task,"FAILED","排队超时，请重新提交"));
    }
}
