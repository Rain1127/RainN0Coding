package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import java.util.Set;

@Component
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationTaskRecovery {
    private final GenerationTaskStore store;
    private final GenerationWork work;
    private final GenerationQueueProperties config;
    private final GenerationTaskExecutor executor;

    public GenerationTaskRecovery(GenerationTaskStore store,GenerationWork work,GenerationQueueProperties config,GenerationTaskExecutor executor) {
        this.store=store;this.work=work;this.config=config;this.executor=executor;
    }
    public boolean infrastructureHealthy() {
        if(store.paused())return false;
        work.busy(0); // Authenticated bounded probe; no model call and no task is created.
        return true;
    }
    public void completeFailed(GenerationTaskStore.Task task) {
        work.completeHistory(task,"FAILED","任务无法执行或重试次数已用尽，请检查失败记录");
    }
    public void recover() {
        if(store.paused())return;
        for(var task:store.recoveryCandidates()) {
            if(!config.isAutoRecoveryEnabled()&&"INTERRUPTED".equals(task.status()))continue;
            if(executor.isExecuting(task.taskId()))continue;
            if(work.busy(task.appId()))continue;
            String status;
            try {
                Object value=work.status(task.userId(),task.appId(),task.taskId()).get("status");
                status=value instanceof String text?text:"unknown";
            } catch(BusinessException e) {
                if(e.getCode()!=ErrorCode.NOT_FOUND_ERROR.getCode())throw e;
                status="missing";
            }
            // running/pausing or an unknown response is never proof that starting again is safe.
            if(!Set.of("missing","paused","interrupted","completed","failed").contains(status))continue;
            boolean checkpoint=!"missing".equals(status),failed="failed".equals(status);
            store.recover(task,checkpoint,failed,
                    ()->work.completeHistory(task,config.isAutoRecoveryEnabled()?"FAILED":"INTERRUPTED",
                            config.isAutoRecoveryEnabled()?"任务无法自动恢复，请检查失败记录":"自动恢复已关闭，请手动继续任务"));
        }
    }
}
