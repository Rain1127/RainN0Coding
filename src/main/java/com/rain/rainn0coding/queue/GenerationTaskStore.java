package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.GenerationLeaseLostException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Transactions here own task, outbox, history callback and event consistency. */
@Repository
@ConditionalOnProperty(name = "app.generation-queue.enabled", havingValue = "true")
public class GenerationTaskStore {
    public record Task(String taskId, long appId, long userId, String prompt, String codeGenType,
                       String idempotencyKey, String traceId, String status, String errorMessage,
                       long lastEventId, Instant createdAt, String ownerId) {
        public boolean terminal() { return List.of("SUCCEEDED","FAILED","INTERRUPTED").contains(status); }
        public boolean settled() { return terminal() || "PAUSED".equals(status); }
    }
    public record Event(long id, String data) {}
    public record Dispatch(String taskId, long appId, int attempts, int epoch) {}
    private static final RowMapper<Task> TASK = (rs, n) -> new Task(rs.getString("task_id"),
            rs.getLong("app_id"),rs.getLong("user_id"),rs.getString("prompt"),rs.getString("code_gen_type"),
            rs.getString("idempotency_key"),rs.getString("trace_id"),rs.getString("status"),
            rs.getString("error_message"),rs.getLong("last_event_id"),rs.getTimestamp("created_at").toInstant(),rs.getString("owner_id"));
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final GenerationQueueProperties config;

    public GenerationTaskStore(JdbcTemplate jdbc, PlatformTransactionManager manager, GenerationQueueProperties config) {
        this.jdbc=jdbc; this.tx=new TransactionTemplate(manager); this.config=config;
    }

    public Task submit(long appId, long userId, String prompt, String type, String key, String trace, Runnable accepted) {
        return tx.execute(s -> {
            // One database mutex serializes admission across JVMs; COUNT alone would race.
            jdbc.queryForObject("SELECT id FROM generation_queue_lock WHERE id=1 FOR UPDATE", Integer.class);
            var existing = jdbc.query("SELECT * FROM generation_task WHERE user_id=? AND app_id=? AND idempotency_key=?", TASK,userId,appId,key);
            if (!existing.isEmpty()) {
                Task old=existing.getFirst();
                if(!old.prompt().equals(prompt) || !old.codeGenType().equals(type))
                    throw new BusinessException(ErrorCode.REQUEST_REPLAY_CONFLICT);
                return old;
            }
            if(paused())throw new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED,"生成服务正在维护，请稍后再试");
            if(jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE active_app_id=?",Long.class,appId)>0)
                throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS,"该应用已有生成任务，请等待完成");
            if(jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE active_app_id IS NOT NULL",Long.class)>=config.getMaxPending())
                throw new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED,"生成队列已满，请稍后再试");
            String id=UUID.randomUUID().toString();
            jdbc.update("INSERT INTO generation_task(task_id,app_id,user_id,prompt,code_gen_type,idempotency_key,trace_id,status,active_app_id) VALUES(?,?,?,?,?,?,?,'QUEUED',?)",id,appId,userId,prompt,type,key,trace,appId);
            jdbc.update("INSERT INTO generation_outbox(task_id,app_id) VALUES(?,?)",id,appId);
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","queued","phase","queued","message","任务已排队","taskId",id)));
            accepted.run();
            return get(id);
        });
    }
    public Task get(String id) {
        var tasks=jdbc.query("SELECT * FROM generation_task WHERE task_id=?",TASK,id);
        return tasks.isEmpty()?null:tasks.getFirst();
    }
    public Task latest(long app,long user) {
        var rows=jdbc.query("SELECT * FROM generation_task WHERE app_id=? AND user_id=? ORDER BY created_at DESC, task_id DESC LIMIT 1",TASK,app,user);
        return rows.isEmpty()?null:rows.getFirst();
    }
    public Task byRequest(long app,long user,String key) {
        var rows=jdbc.query("SELECT * FROM generation_task WHERE app_id=? AND user_id=? AND idempotency_key=?",TASK,app,user,key);
        return rows.isEmpty()?null:rows.getFirst();
    }
    public Task active(long app) {
        var rows=jdbc.query("SELECT * FROM generation_task WHERE active_app_id=?",TASK,app);
        return rows.isEmpty()?null:rows.getFirst();
    }
    public boolean claim(String id,String owner) {
        return Boolean.TRUE.equals(tx.execute(s -> {
            if(jdbc.queryForObject("SELECT paused FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class)!=0)return false;
            jdbc.queryForList("SELECT task_id FROM generation_task WHERE task_id=? FOR UPDATE",String.class,id);
            ensureExecution(id);
            if(jdbc.queryForObject("SELECT COUNT(*) FROM generation_execution WHERE task_id=? AND next_attempt_at>CURRENT_TIMESTAMP(6)",Integer.class,id)>0)return false;
            int updated=jdbc.update("UPDATE generation_task SET status='RUNNING',owner_id=?,started_at=CURRENT_TIMESTAMP WHERE task_id=? AND status='QUEUED'",owner,id);
            if(updated==0)return false;
            jdbc.update("UPDATE generation_execution SET heartbeat_at=CURRENT_TIMESTAMP(6),lease_until=?,recoverable=0,failure_kind=NULL WHERE task_id=?",
                    Timestamp.from(Instant.now().plusSeconds(config.getLeaseSeconds())),id);
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","progress","phase","starting","message","开始生成")));
            return true;
        }));
    }
    public boolean paused() {return jdbc.queryForObject("SELECT paused FROM generation_queue_lock WHERE id=1",Integer.class)!=0;}
    public void setPaused(boolean paused) {jdbc.update("UPDATE generation_queue_lock SET paused=? WHERE id=1",paused?1:0);}
    public boolean shouldResume(String id) {
        return jdbc.queryForObject("SELECT resume_requested FROM generation_task WHERE task_id=?",Integer.class,id)!=0;
    }
    public boolean pauseQueued(String id) {
        return Boolean.TRUE.equals(tx.execute(s->{
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id);
            if(rows.isEmpty()||!"QUEUED".equals(rows.getFirst().status()))return false;
            pauseLocked(id,false);return true;
        }));
    }
    public void markPausing(String id) {
        tx.executeWithoutResult(s->{
            if(jdbc.update("UPDATE generation_task SET status='PAUSING' WHERE task_id=? AND status='RUNNING'",id)>0)
                appendLocked(id,JSONUtil.toJsonStr(Map.of("type","progress","phase","pausing","message","正在保存暂停检查点")));
        });
    }
    public void pauseCompleted(String id,boolean checkpoint) {
        tx.executeWithoutResult(s->{
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id);
            if(!rows.isEmpty()&&List.of("RUNNING","PAUSING").contains(rows.getFirst().status()))pauseLocked(id,checkpoint);
        });
    }
    private void pauseLocked(String id,boolean checkpoint) {
        jdbc.update("UPDATE generation_task SET status='PAUSED',resume_requested=CASE WHEN ?=1 THEN 1 ELSE resume_requested END WHERE task_id=?",checkpoint?1:0,id);
        appendLocked(id,JSONUtil.toJsonStr(Map.of("type","done","status","paused","message","任务已暂停")));
    }
    public Task resume(String id,boolean checkpoint) {
        return tx.execute(s->{
            jdbc.queryForObject("SELECT id FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class);
            var task=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id).getFirst();
            if(List.of("QUEUED","RUNNING","PAUSING").contains(task.status()))return task;
            if(!List.of("PAUSED","INTERRUPTED").contains(task.status()))throw new BusinessException(ErrorCode.PARAMS_ERROR,"任务不可继续");
            if(paused())throw new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED,"生成服务正在维护");
            ensureExecution(id);
            jdbc.update("UPDATE generation_execution SET retries=0,recoverable=0,failure_kind=NULL,next_attempt_at=CURRENT_TIMESTAMP(6) WHERE task_id=?",id);
            jdbc.update("UPDATE generation_task SET status='QUEUED',resume_requested=?,owner_id=NULL,error_message=NULL,ended_at=NULL,queued_at=CURRENT_TIMESTAMP(6) WHERE task_id=?",checkpoint?1:0,id);
            jdbc.update("UPDATE generation_outbox SET published=0,attempts=0,dispatch_epoch=dispatch_epoch+1,next_attempt_at=CURRENT_TIMESTAMP WHERE task_id=?",id);
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","queued","phase","queued","message","继续任务已排队")));
            return get(id);
        });
    }
    public Task importLegacyPaused(String id,long appId,long userId,String type) {
        return tx.execute(s->{
            jdbc.queryForObject("SELECT id FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class);
            var existing=get(id);
            if(existing!=null) {
                if(existing.appId()!=appId||existing.userId()!=userId)throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
                return existing;
            }
            if(active(appId)!=null)throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS);
            if(jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE active_app_id IS NOT NULL",Long.class)>=config.getMaxPending())
                throw new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED);
            jdbc.update("INSERT INTO generation_task(task_id,app_id,user_id,prompt,code_gen_type,idempotency_key,status,active_app_id,resume_requested) VALUES(?,?,?,'',?,?,'PAUSED',?,1)",id,appId,userId,type,"legacy:"+id,appId);
            jdbc.update("INSERT INTO generation_outbox(task_id,app_id,published) VALUES(?,?,1)",id,appId);
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","done","status","paused","message","已恢复原任务")));
            return get(id);
        });
    }
    public void append(String id,String data) {
        tx.executeWithoutResult(s -> {
            var t=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id).getFirst();
            if(t.terminal())return;
            if(t.lastEventId()>=config.getMaxEventsPerTask() || data.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>config.getMaxEventBytes())
                throw new IllegalStateException("生成进度超出存储限制");
            appendLocked(id,data);
        });
    }
    private void appendLocked(String id,String data) {
        jdbc.update("UPDATE generation_task SET last_event_id=last_event_id+1 WHERE task_id=?",id);
        Long sequence=jdbc.queryForObject("SELECT last_event_id FROM generation_task WHERE task_id=?",Long.class,id);
        jdbc.update("INSERT INTO generation_event(task_id,event_id,data) VALUES(?,?,?)",id,sequence,data);
    }
    public boolean finish(String id,String status,String message,Runnable completion) {
        return finish(id,status,message,completion,false);
    }
    public boolean finishQueued(String id,String message,Runnable completion) {
        return finish(id,"FAILED",message,completion,true);
    }
    private boolean finish(String id,String status,String message,Runnable completion,boolean queuedOnly) {
        return finish(id,status,message,completion,queuedOnly,false);
    }
    private boolean finish(String id,String status,String message,Runnable completion,boolean queuedOnly,boolean allowInterrupted) {
        if(!List.of("SUCCEEDED","FAILED","INTERRUPTED").contains(status))throw new IllegalArgumentException("invalid terminal state");
        return Boolean.TRUE.equals(tx.execute(s -> {
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id);
            if(rows.isEmpty()||(rows.getFirst().settled()&&!(allowInterrupted&&"INTERRUPTED".equals(rows.getFirst().status()))))return false;
            if(queuedOnly&&!"QUEUED".equals(rows.getFirst().status()))return false;
            String safe=message==null?null:message.substring(0,Math.min(message.length(),1000));
            // Interrupted runs retain the app reservation until Python is confirmed idle.
            jdbc.update("UPDATE generation_task SET status=?,error_message=?,ended_at=CURRENT_TIMESTAMP,active_app_id=? WHERE task_id=?",status,safe,"INTERRUPTED".equals(status)?rows.getFirst().appId():null,id);
            if(!"SUCCEEDED".equals(status)) appendLocked(id,JSONUtil.toJsonStr(Map.of("type","error","status",status.toLowerCase(),"message",safe==null?"生成失败":safe)));
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","done","status","SUCCEEDED".equals(status)?"success":status.toLowerCase())));
            completion.run();
            return true;
        }));
    }
    public List<Task> running() {return jdbc.query("SELECT * FROM generation_task WHERE status IN ('RUNNING','PAUSING')",TASK);}
    public List<Task> expired() {
        return jdbc.query("SELECT * FROM generation_task WHERE status='QUEUED' AND queued_at<? LIMIT 100",TASK,Timestamp.from(Instant.now().minus(config.getMaxWaitHours(),ChronoUnit.HOURS)));
    }
    public List<Event> events(String id,long after) {
        return jdbc.query("SELECT event_id,data FROM generation_event WHERE task_id=? AND event_id>? ORDER BY event_id LIMIT 100",(r,n)->new Event(r.getLong(1),r.getString(2)),id,after);
    }
    public List<Dispatch> pendingDispatches() {
        return jdbc.query("SELECT o.task_id,o.app_id,o.attempts,o.dispatch_epoch FROM generation_outbox o JOIN generation_task t ON t.task_id=o.task_id LEFT JOIN generation_execution e ON e.task_id=t.task_id WHERE o.published=0 AND o.next_attempt_at<=CURRENT_TIMESTAMP AND (e.task_id IS NULL OR e.next_attempt_at<=CURRENT_TIMESTAMP(6)) AND t.status='QUEUED' ORDER BY t.queued_at LIMIT 20",(r,n)->new Dispatch(r.getString(1),r.getLong(2),r.getInt(3),r.getInt(4)));
    }
    public void dispatched(String id) {jdbc.update("UPDATE generation_outbox SET published=1 WHERE task_id=?",id);}
    public void dispatched(Dispatch dispatch) {jdbc.update("UPDATE generation_outbox SET published=1 WHERE task_id=? AND dispatch_epoch=?",dispatch.taskId(),dispatch.epoch());}
    public void dispatchFailed(Dispatch d) {
        long wait=Math.min(60,1L<<Math.min(d.attempts(),6));
        jdbc.update("UPDATE generation_outbox SET attempts=attempts+1,next_attempt_at=? WHERE task_id=? AND dispatch_epoch=?",Timestamp.from(Instant.now().plusSeconds(wait)),d.taskId(),d.epoch());
    }
    public long count(String status) {return jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE status=?",Long.class,status);}
    public long waitMillis(String id) {
        Timestamp queued=jdbc.queryForObject("SELECT queued_at FROM generation_task WHERE task_id=?",Timestamp.class,id);
        return Math.max(0,java.time.Duration.between(queued.toInstant(),Instant.now()).toMillis());
    }
    public void cleanupEvents() {
        var tasks=jdbc.queryForList("SELECT t.task_id FROM generation_task t WHERE status IN ('SUCCEEDED','FAILED') AND ended_at<? AND EXISTS (SELECT 1 FROM generation_event e WHERE e.task_id=t.task_id) LIMIT 100",String.class,Timestamp.from(Instant.now().minus(config.getEventRetentionDays(),ChronoUnit.DAYS)));
        for(String id:tasks) jdbc.update("DELETE FROM generation_event WHERE task_id=?",id);
    }

    private void ensureExecution(String id) {
        jdbc.update("INSERT IGNORE INTO generation_execution(task_id) VALUES (?)",id);
    }
    public boolean owns(String id,String owner) {
        if(owner==null)return false;
        return jdbc.queryForObject("SELECT COUNT(*) FROM generation_task t JOIN generation_execution e ON t.task_id=e.task_id WHERE t.task_id=? AND t.owner_id=? AND t.status IN ('RUNNING','PAUSING') AND e.lease_until>CURRENT_TIMESTAMP(6) AND e.recoverable=0",Integer.class,id,owner)>0;
    }
    private void requireOwner(String id,String owner) {
        jdbc.queryForList("SELECT task_id FROM generation_task WHERE task_id=? FOR UPDATE",String.class,id);
        if(!owns(id,owner))throw new GenerationLeaseLostException();
    }
    public void heartbeat(String id,String owner) {
        tx.executeWithoutResult(s->{
            requireOwner(id,owner);
            jdbc.update("UPDATE generation_execution SET heartbeat_at=CURRENT_TIMESTAMP(6),lease_until=? WHERE task_id=?",
                    Timestamp.from(Instant.now().plusSeconds(config.getLeaseSeconds())),id);
        });
    }
    public void appendOwned(String id,String owner,String data) {
        tx.executeWithoutResult(s->{requireOwner(id,owner);append(id,data);});
    }
    public void pauseOwned(String id,String owner) {
        tx.executeWithoutResult(s->{requireOwner(id,owner);pauseCompleted(id,true);});
    }
    public void finishOwned(String id,String owner,String status,String message,Runnable completion) {
        tx.executeWithoutResult(s->{
            requireOwner(id,owner);
            if(!"SUCCEEDED".equals(status))quarantine("task:"+id,id,"execution_failed");
            finish(id,status,message,completion);
        });
    }
    public boolean finalized(String id) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM generation_execution WHERE task_id=? AND finalized=1",Integer.class,id)>0;
    }
    public void markFinalized(String id,String owner) {
        tx.executeWithoutResult(s->{requireOwner(id,owner);jdbc.update("UPDATE generation_execution SET finalized=1 WHERE task_id=?",id);});
    }
    public void quarantine(String key,String taskId,String reason) {
        // Only identifiers and fixed reason codes; never persist untrusted message bodies or exception secrets.
        jdbc.update("INSERT IGNORE INTO generation_failure(failure_key,task_id,reason) VALUES (?,?,?)",key,taskId,reason);
    }
    public void rejectQueued(Task task,Runnable completion) {
        tx.executeWithoutResult(s->{
            if(finishQueued(task.taskId(),"任务无法执行，请检查失败记录",completion))
                quarantine("task:"+task.taskId(),task.taskId(),"invalid_task");
        });
    }
    public void requestRecovery(String id,String owner,GenerationFailurePolicy.Kind kind) {
        tx.executeWithoutResult(s->{
            requireOwner(id,owner);
            jdbc.update("UPDATE generation_execution SET recoverable=1,failure_kind=?,next_attempt_at=? WHERE task_id=?",
                    kind.name(),Timestamp.from(Instant.now().plusSeconds(GenerationFailurePolicy.delaySeconds(config,retries(id)))),id);
        });
    }
    public List<Task> recoveryCandidates() {
        return jdbc.query("SELECT t.* FROM generation_task t LEFT JOIN generation_execution e ON e.task_id=t.task_id WHERE t.status IN ('RUNNING','PAUSING','INTERRUPTED') AND (e.task_id IS NULL OR ((e.recoverable=1 OR e.lease_until<CURRENT_TIMESTAMP(6)) AND e.next_attempt_at<=CURRENT_TIMESTAMP(6))) ORDER BY t.created_at LIMIT 100",TASK);
    }
    public boolean terminalRecovery(String id) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM generation_execution WHERE task_id=? AND failure_kind='TERMINAL'",Integer.class,id)>0;
    }
    public int retries(String id) {
        ensureExecution(id);
        return jdbc.queryForObject("SELECT retries FROM generation_execution WHERE task_id=?",Integer.class,id);
    }
    public void delayQueued(String id,boolean countRetry,Runnable completion) {
        tx.executeWithoutResult(s->{
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id);
            if(rows.isEmpty()||!"QUEUED".equals(rows.getFirst().status()))return;
            int retries=retries(id);
            if(countRetry&&retries>=config.getMaxRetries()) {
                quarantine("task:"+id,id,"retries_exhausted");
                finishQueued(id,"任务重试次数已用尽，请检查失败记录",completion);return;
            }
            var next=Timestamp.from(Instant.now().plusSeconds(GenerationFailurePolicy.delaySeconds(config,retries)));
            jdbc.update("UPDATE generation_execution SET retries=retries+?,next_attempt_at=? WHERE task_id=?",countRetry?1:0,next,id);
            jdbc.update("UPDATE generation_outbox SET published=0,dispatch_epoch=dispatch_epoch+1,next_attempt_at=? WHERE task_id=?",next,id);
        });
    }
    public void recover(Task expected,boolean checkpoint,boolean failed,Runnable completion) {
        tx.executeWithoutResult(s->{
            jdbc.queryForObject("SELECT id FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class);
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,expected.taskId());
            if(rows.isEmpty()||paused())return;
            var task=rows.getFirst();
            if(!java.util.Objects.equals(task.ownerId(),expected.ownerId())||!task.status().equals(expected.status()))return;
            // A current owner may have renewed its lease while the recovery probe was in flight.
            if(task.ownerId()!=null&&owns(task.taskId(),task.ownerId()))return;
            if("PAUSING".equals(task.status())&&!failed&&!terminalRecovery(task.taskId())) {pauseCompleted(task.taskId(),checkpoint);return;}
            if(!List.of("RUNNING","PAUSING","INTERRUPTED").contains(task.status()))return;
            if(!config.isAutoRecoveryEnabled()) {
                finish(task.taskId(),"INTERRUPTED","自动恢复已关闭，请手动继续任务",completion);return;
            }
            if(failed||terminalRecovery(task.taskId())||retries(task.taskId())>=config.getMaxRetries()) {
                quarantine("task:"+task.taskId(),task.taskId(),failed?"python_failed":"recovery_exhausted");
                finish(task.taskId(),"FAILED","任务无法自动恢复，请检查失败记录",
                        "INTERRUPTED".equals(task.status())?()->{}:completion,false,true);return;
            }
            ensureExecution(task.taskId());
            jdbc.update("UPDATE generation_execution SET retries=retries+1,recoverable=0,failure_kind=NULL,next_attempt_at=CURRENT_TIMESTAMP(6) WHERE task_id=?",task.taskId());
            jdbc.update("UPDATE generation_task SET status='QUEUED',resume_requested=?,owner_id=NULL,error_message=NULL,ended_at=NULL,queued_at=CURRENT_TIMESTAMP(6) WHERE task_id=?",checkpoint?1:0,task.taskId());
            jdbc.update("UPDATE generation_outbox SET published=0,attempts=0,dispatch_epoch=dispatch_epoch+1,next_attempt_at=CURRENT_TIMESTAMP WHERE task_id=?",task.taskId());
            appendLocked(task.taskId(),JSONUtil.toJsonStr(Map.of("type","queued","phase","recovering","message","正在从已保存进度恢复任务")));
        });
    }
}
