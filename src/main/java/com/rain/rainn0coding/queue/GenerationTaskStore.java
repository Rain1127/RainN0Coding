package com.rain.rainn0coding.queue;

import cn.hutool.json.JSONUtil;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
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
        public boolean terminal() { return !"QUEUED".equals(status) && !"RUNNING".equals(status); }
    }
    public record Event(long id, String data) {}
    public record Dispatch(String taskId, long appId, int attempts) {}
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
            if(jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE status IN ('QUEUED','RUNNING')",Long.class)>=config.getMaxPending())
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
    public Task active(long app) {
        var rows=jdbc.query("SELECT * FROM generation_task WHERE active_app_id=?",TASK,app);
        return rows.isEmpty()?null:rows.getFirst();
    }
    public boolean claim(String id,String owner) {
        return Boolean.TRUE.equals(tx.execute(s -> {
            if(jdbc.queryForObject("SELECT paused FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class)!=0)return false;
            int updated=jdbc.update("UPDATE generation_task SET status='RUNNING',owner_id=?,started_at=CURRENT_TIMESTAMP WHERE task_id=? AND status='QUEUED'",owner,id);
            if(updated==0)return false;
            appendLocked(id,JSONUtil.toJsonStr(Map.of("type","progress","phase","starting","message","开始生成")));
            return true;
        }));
    }
    public boolean paused() {return jdbc.queryForObject("SELECT paused FROM generation_queue_lock WHERE id=1",Integer.class)!=0;}
    public void setPaused(boolean paused) {jdbc.update("UPDATE generation_queue_lock SET paused=? WHERE id=1",paused?1:0);}
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
        if(!List.of("SUCCEEDED","FAILED","INTERRUPTED").contains(status))throw new IllegalArgumentException("invalid terminal state");
        return Boolean.TRUE.equals(tx.execute(s -> {
            var rows=jdbc.query("SELECT * FROM generation_task WHERE task_id=? FOR UPDATE",TASK,id);
            if(rows.isEmpty()||rows.getFirst().terminal())return false;
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
    public void releaseInterrupted(long app) {
        jdbc.update("UPDATE generation_task SET active_app_id=NULL WHERE active_app_id=? AND status='INTERRUPTED'",app);
    }
    public List<Task> running() {return jdbc.query("SELECT * FROM generation_task WHERE status='RUNNING'",TASK);}
    public List<Task> expired() {
        return jdbc.query("SELECT * FROM generation_task WHERE status='QUEUED' AND created_at<? LIMIT 100",TASK,Timestamp.from(Instant.now().minus(config.getMaxWaitHours(),ChronoUnit.HOURS)));
    }
    public List<Event> events(String id,long after) {
        return jdbc.query("SELECT event_id,data FROM generation_event WHERE task_id=? AND event_id>? ORDER BY event_id LIMIT 100",(r,n)->new Event(r.getLong(1),r.getString(2)),id,after);
    }
    public List<Dispatch> pendingDispatches() {
        return jdbc.query("SELECT o.task_id,o.app_id,o.attempts FROM generation_outbox o JOIN generation_task t ON t.task_id=o.task_id WHERE o.published=0 AND o.next_attempt_at<=CURRENT_TIMESTAMP AND t.status='QUEUED' ORDER BY t.created_at LIMIT 20",(r,n)->new Dispatch(r.getString(1),r.getLong(2),r.getInt(3)));
    }
    public void dispatched(String id) {jdbc.update("UPDATE generation_outbox SET published=1 WHERE task_id=?",id);}
    public void dispatchFailed(Dispatch d) {
        long wait=Math.min(60,1L<<Math.min(d.attempts(),6));
        jdbc.update("UPDATE generation_outbox SET attempts=attempts+1,next_attempt_at=? WHERE task_id=?",Timestamp.from(Instant.now().plusSeconds(wait)),d.taskId());
    }
    public long count(String status) {return jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE status=?",Long.class,status);}
    public void cleanupEvents() {
        var tasks=jdbc.queryForList("SELECT task_id FROM generation_task WHERE status IN ('SUCCEEDED','FAILED','INTERRUPTED') AND ended_at<? LIMIT 100",String.class,Timestamp.from(Instant.now().minus(config.getEventRetentionDays(),ChronoUnit.DAYS)));
        for(String id:tasks) jdbc.update("DELETE FROM generation_event WHERE task_id=?",id);
    }
}
