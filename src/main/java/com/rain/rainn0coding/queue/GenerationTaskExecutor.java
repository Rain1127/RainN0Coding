package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
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
    private static final Set<String> SUCCESS=Set.of("success","partial_success","degraded_success");
    private final GenerationTaskStore store;
    private final GenerationWork work;
    private final GenerationQueueProperties config;
    private final String owner=UUID.randomUUID().toString();
    public GenerationTaskExecutor(GenerationTaskStore store,GenerationWork work,GenerationQueueProperties config) {
        this.store=store;this.work=work;this.config=config;
    }
    public void execute(String id) {
        var task=store.get(id);
        if(task==null||task.settled())return;
        if("RUNNING".equals(task.status())||"PAUSING".equals(task.status())) {
            finish(task,"INTERRUPTED","执行中断，原执行结束后可以重试");
            return;
        }
        if(work.busy(task.appId()))throw new IllegalStateException("上次生成仍在结束中");
        if(!store.claim(id,owner)) {
            var current=store.get(id);
            if(current!=null&&"QUEUED".equals(current.status()))throw new IllegalStateException("生成队列暂停消费");
            return;
        }
        var successfulDone=new AtomicBoolean(false);
        var pausedDone=new AtomicBoolean(false);
        var failure=new AtomicReference<String>();
        String status="SUCCEEDED";
        String message=null;
        try {
            work.stream(task).publishOn(Schedulers.boundedElastic(),1)
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
                        store.append(id,json);
                    })
                    .takeUntilOther(Mono.delay(Duration.ofMinutes(config.getTaskTimeoutMinutes()))
                            .flatMap(ignored->Mono.error(new IllegalStateException("任务超过最长执行时间"))))
                    .blockLast();
            if(pausedDone.get()&&failure.get()==null) {store.pauseCompleted(id,true);return;}
            if(!successfulDone.get()||failure.get()!=null) {
                status="FAILED"; message=failure.get()!=null?failure.get():"生成连接结束但没有成功结果";
            }
        } catch(Exception e) {
            log.warn("Generation task {} execution failed: {}",id,e.toString());
            status="FAILED"; message="生成执行失败，请重试或联系管理员";
            try {if(work.busy(task.appId()))status="INTERRUPTED";}
            catch(Exception unavailable) {status="INTERRUPTED";}
        }
        // Persistence exceptions propagate to Kafka; a redelivery never reruns a claimed task.
        finish(task,status,message);
    }
    private void finish(GenerationTaskStore.Task task,String status,String message) {
        store.finish(task.taskId(),status,message,()->work.completeHistory(task,status,message));
    }
    public void recoverInterrupted() {
        for(var task:store.running()) finish(task,"INTERRUPTED","服务重启导致执行中断，原执行结束后可以重试");
    }
    public void expireQueued() {
        for(var task:store.expired()) store.finishQueued(task.taskId(),"排队超时，请重新提交",
                ()->work.completeHistory(task,"FAILED","排队超时，请重新提交"));
    }
}
