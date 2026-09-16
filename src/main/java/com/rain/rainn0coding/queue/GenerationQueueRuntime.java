package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

@Component
@Slf4j
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationQueueRuntime {
    private final GenerationTaskStore store;
    private final GenerationTaskExecutor executor;
    private final GenerationQueueProperties config;
    private final KafkaTemplate<String,String> kafka;
    private final KafkaListenerEndpointRegistry listeners;
    private final MeterRegistry meters;
    private volatile boolean ready;
    private final AtomicLong queued=new AtomicLong(),running=new AtomicLong();
    public GenerationQueueRuntime(GenerationTaskStore store,GenerationTaskExecutor executor,GenerationQueueProperties config,
            KafkaTemplate<String,String> kafka,KafkaListenerEndpointRegistry listeners,MeterRegistry meters) {
        this.store=store;this.executor=executor;this.config=config;this.kafka=kafka;this.listeners=listeners;this.meters=meters;
        meters.gauge("generation.queue.pending",queued);
        meters.gauge("generation.queue.running",running);
    }
    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        if(config.getMaxPending()<1||config.getTaskTimeoutMinutes()<1||config.getMaxWaitHours()<1)throw new IllegalArgumentException("Invalid generation queue limits");
        executor.recoverInterrupted();
        ready=true;
        var container=listeners.getListenerContainer("generationTasks");
        if(container!=null)container.start();
    }
    @Scheduled(fixedDelay=2000)
    public void dispatch() {
        if(!ready)return;
        try {
            for(var d:store.pendingDispatches()) {
                try {
                    kafka.send(config.getTopic(),String.valueOf(d.appId()),JSONUtil.toJsonStr(Map.of("version",1,"taskId",d.taskId())))
                            .get(12,TimeUnit.SECONDS);
                    store.dispatched(d.taskId());
                } catch(Exception e) {
                    if(e instanceof InterruptedException)Thread.currentThread().interrupt();
                    store.dispatchFailed(d);
                    meters.counter("generation.queue.dispatch.retries").increment();
                    log.warn("Generation task dispatch pending: {}",d.taskId());
                    break;
                }
            }
        } catch(Exception e) {log.warn("Generation outbox temporarily unavailable: {}",e.toString());}
    }
    @KafkaListener(id="generationTasks",topics="${app.generation-queue.topic:rain-code-generation-v1}",
            groupId="${app.generation-queue.group-id:rain-code-generation-workers-v1}",containerFactory="generationKafkaListenerFactory")
    public void consume(ConsumerRecord<String,String> record,Acknowledgment ack) {
        String id;
        try {
            var msg=JSONUtil.parseObj(record.value());
            if(msg.getInt("version",0)!=1)throw new IllegalArgumentException("unknown schema");
            id=msg.getStr("taskId"); java.util.UUID.fromString(id);
        } catch(Exception malformed) {
            meters.counter("generation.queue.invalid.messages").increment();
            log.error("Invalid generation message at partition {} offset {}",record.partition(),record.offset());
            ack.acknowledge(); return;
        }
        long start=System.nanoTime();
        executor.execute(id);
        meters.timer("generation.queue.delivery.duration").record(System.nanoTime()-start,TimeUnit.NANOSECONDS);
        ack.acknowledge();
    }
    @Scheduled(fixedDelay=30000)
    public void maintenance() {
        if(!ready)return;
        try {
            executor.expireQueued();
            queued.set(store.count("QUEUED"));running.set(store.count("RUNNING"));
        } catch(Exception e) {log.warn("Generation queue maintenance failed: {}",e.toString());}
    }
    @Scheduled(fixedDelay=3600000)
    public void cleanup() {if(ready)store.cleanupEvents();}
}
