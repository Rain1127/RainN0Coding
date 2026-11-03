package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.GenerationLeaseLostException;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.Acknowledgment;
import reactor.core.publisher.Flux;
import java.time.Duration;
import java.time.Instant;
import java.sql.Timestamp;
import java.util.Map;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class GenerationQueueReliabilityTest {
    JdbcTemplate jdbc;
    GenerationTaskStore store;
    GenerationQueueProperties config;
    GenerationWork work;
    GenerationTaskRecovery recovery;
    @BeforeEach void setup() {
        var ds=new DriverManagerDataSource("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1","sa","");
        var migration=new ResourceDatabasePopulator(new ClassPathResource("sql/generation-queue.sql"),
                new ClassPathResource("sql/generation-queue-reliability.sql"));
        migration.execute(ds);
        migration.execute(ds); // Both migrations are additive and repeatable.
        jdbc=new JdbcTemplate(ds);config=new GenerationQueueProperties();
        store=new GenerationTaskStore(jdbc,new DataSourceTransactionManager(ds),config);
        work=mock(GenerationWork.class);recovery=new GenerationTaskRecovery(store,work,config,new GenerationTaskExecutor(store,work,config));
    }
    GenerationTaskStore.Task task(long app) {
        return store.submit(app,7,"page","html","key","trace",()->{});
    }
    void expire(String id) {
        jdbc.update("UPDATE generation_execution SET lease_until=?,next_attempt_at=? WHERE task_id=?",
                Timestamp.from(Instant.now().minusSeconds(2)),Timestamp.from(Instant.now().minusSeconds(2)),id);
    }
    void status(GenerationTaskStore.Task task,String status) {
        when(work.status(task.userId(),task.appId(),task.taskId())).thenReturn(Map.of("status",status));
    }
    long failures() {return jdbc.queryForObject("SELECT COUNT(*) FROM generation_failure",Long.class);}

    @Test void restartResumesSameTaskAndCheckpointWithoutWritingFailureHistory() {
        var task=task(1);store.claim(task.taskId(),"old");store.dispatched(task.taskId());expire(task.taskId());
        status(task,"interrupted");recovery.recover();
        assertEquals("QUEUED",store.get(task.taskId()).status());
        assertTrue(store.shouldResume(task.taskId()));assertEquals(1,store.pendingDispatches().size());
        verify(work,never()).completeHistory(any(),anyString(),any());
        when(work.stream(any())).thenReturn(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"));
        var executor=new GenerationTaskExecutor(store,work,config);
        executor.execute(task.taskId());executor.execute(task.taskId());
        assertEquals("SUCCEEDED",store.get(task.taskId()).status());
        verify(work,times(1)).stream(any());
        verify(work,times(1)).completeHistory(any(),eq("SUCCEEDED"),isNull());
    }
    @Test void staleOwnerCannotWriteProgressFinalizePauseOrComplete() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());status(task,"interrupted");
        recovery.recover();assertTrue(store.claim(task.taskId(),"new"));
        assertThrows(GenerationLeaseLostException.class,()->store.appendOwned(task.taskId(),"old","{}"));
        assertThrows(GenerationLeaseLostException.class,()->store.markFinalized(task.taskId(),"old"));
        assertThrows(GenerationLeaseLostException.class,()->store.pauseOwned(task.taskId(),"old"));
        assertThrows(GenerationLeaseLostException.class,()->store.finishOwned(task.taskId(),"old","SUCCEEDED",null,()->fail("stale history")));
        assertTrue(store.owns(task.taskId(),"new"));
    }
    @Test void liveLeaseAndBusyPythonBothPreventRecovery() {
        var task=task(1);store.claim(task.taskId(),"old");recovery.recover();
        verifyNoInteractions(work);
        expire(task.taskId());when(work.busy(1)).thenReturn(true);recovery.recover();
        verify(work,never()).status(anyLong(),anyLong(),anyString());
        assertEquals("RUNNING",store.get(task.taskId()).status());assertEquals(0,store.retries(task.taskId()));
    }
    @Test void leaseRenewedDuringProbePreventsTakeover() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());
        when(work.status(7,1,task.taskId())).thenAnswer(call->{
            jdbc.update("UPDATE generation_execution SET lease_until=? WHERE task_id=?",Timestamp.from(Instant.now().plusSeconds(60)),task.taskId());
            return Map.of("status","interrupted");
        });
        recovery.recover();assertEquals("RUNNING",store.get(task.taskId()).status());
    }
    @Test void userRequestedPauseNeverAutoResumes() {
        var task=task(1);store.claim(task.taskId(),"old");store.markPausing(task.taskId());expire(task.taskId());
        status(task,"paused");recovery.recover();recovery.recover();
        assertEquals("PAUSED",store.get(task.taskId()).status());assertTrue(store.pendingDispatches().isEmpty());
        verify(work,never()).completeHistory(any(),anyString(),any());
    }
    @Test void onlyAuthenticatedNotFoundAllowsFreshStart() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());
        when(work.status(7,1,task.taskId())).thenThrow(new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE));
        assertThrows(BusinessException.class,recovery::recover);
        assertEquals("RUNNING",store.get(task.taskId()).status());assertEquals(0,store.retries(task.taskId()));
        doThrow(new BusinessException(ErrorCode.NOT_FOUND_ERROR)).when(work).status(7,1,task.taskId());
        recovery.recover();assertEquals("QUEUED",store.get(task.taskId()).status());assertFalse(store.shouldResume(task.taskId()));
    }
    @Test void failedPythonRunIsQuarantinedAndNeverResumed() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());status(task,"failed");
        recovery.recover();recovery.recover();
        assertEquals("FAILED",store.get(task.taskId()).status());assertEquals(1,failures());
        verify(work,times(1)).completeHistory(any(),eq("FAILED"),anyString());
    }
    @Test void repeatedCrashesExhaustRecoveryBudgetInsteadOfLoopingForever() {
        config.setMaxRetries(1);var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());status(task,"interrupted");
        recovery.recover();assertTrue(store.claim(task.taskId(),"next"));expire(task.taskId());recovery.recover();
        assertEquals("FAILED",store.get(task.taskId()).status());assertEquals(1,failures());
    }
    @Test void durableDelayedRetryDoesNotConsumeAnEarlyDuplicate() {
        var task=task(1);store.dispatched(task.taskId());store.delayQueued(task.taskId(),true,()->{});
        assertFalse(store.claim(task.taskId(),"early"));assertTrue(store.pendingDispatches().isEmpty());
        jdbc.update("UPDATE generation_execution SET next_attempt_at=? WHERE task_id=?",Timestamp.from(Instant.now().minusSeconds(2)),task.taskId());
        jdbc.update("UPDATE generation_outbox SET next_attempt_at=? WHERE task_id=?",Timestamp.from(Instant.now().minusSeconds(2)),task.taskId());
        assertEquals(1,store.pendingDispatches().size());assertTrue(store.claim(task.taskId(),"due"));
    }
    @Test void failedCompletionRollsBackFailureRecordAndTerminalStateTogether() {
        var task=task(1);store.claim(task.taskId(),"owner");
        assertThrows(IllegalStateException.class,()->store.finishOwned(task.taskId(),"owner","FAILED","bad",()->{throw new IllegalStateException();}));
        assertEquals("RUNNING",store.get(task.taskId()).status());assertEquals(0,failures());
    }
    @Test void unknownStatusNeverCreatesFreshGeneration() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());status(task,"unknown");
        recovery.recover();assertEquals("RUNNING",store.get(task.taskId()).status());assertEquals(0,store.retries(task.taskId()));
    }
    @Test void heartbeatRenewsLeaseEvenWithoutProgressEvents() {
        config.setHeartbeatSeconds(1);config.setLeaseSeconds(3);
        var task=task(1);
        when(work.stream(any())).thenReturn(Flux.just("{\"type\":\"done\",\"status\":\"success\"}").delayElements(Duration.ofMillis(2200)));
        new GenerationTaskExecutor(store,work,config).execute(task.taskId());
        var heartbeat=jdbc.queryForObject("SELECT heartbeat_at FROM generation_execution WHERE task_id=?",Timestamp.class,task.taskId());
        var started=jdbc.queryForObject("SELECT started_at FROM generation_task WHERE task_id=?",Timestamp.class,task.taskId());
        assertTrue(heartbeat.toInstant().isAfter(started.toInstant().plusSeconds(1)));
        assertEquals("SUCCEEDED",store.get(task.taskId()).status());
    }
    @Test void terminalPoisonTaskDoesNotBlockNextTask() {
        var first=task(1);var next=task(2);
        when(work.stream(any())).thenAnswer(call->{
            GenerationTaskStore.Task task=call.getArgument(0);
            return task.appId()==1?Flux.error(new IllegalArgumentException("bad generated event")):
                    Flux.just("{\"type\":\"done\",\"status\":\"success\"}");
        });
        var executor=new GenerationTaskExecutor(store,work,config);
        executor.execute(first.taskId());executor.execute(next.taskId());
        assertEquals("FAILED",store.get(first.taskId()).status());assertEquals("SUCCEEDED",store.get(next.taskId()).status());
        assertEquals(1,failures());
    }
    @Test void infrastructureFailurePausesContainerWithoutAckAndResumesAfterProbe() {
        var task=task(1);var executor=mock(GenerationTaskExecutor.class);
        var registry=mock(KafkaListenerEndpointRegistry.class);var container=mock(MessageListenerContainer.class);
        when(registry.getListenerContainer("generationTasks")).thenReturn(container);
        var runtime=new GenerationQueueRuntime(store,executor,config,mock(KafkaTemplate.class),registry,new SimpleMeterRegistry(),recovery);
        runtime.start();var ack=mock(Acknowledgment.class);
        doThrow(new DataAccessResourceFailureException("offline")).when(executor).execute(task.taskId());
        var record=new ConsumerRecord<String,String>("tasks",0,1,"1","{\"version\":1,\"taskId\":\""+task.taskId()+"\"}");
        assertThrows(DataAccessResourceFailureException.class,()->runtime.consume(record,ack));
        verify(container).pause();verifyNoInteractions(ack);assertEquals(0,store.retries(task.taskId()));
        runtime.maintenance();verify(container).resume();
        reset(executor);runtime.consume(record,ack);verify(ack).acknowledge();
    }
    @Test void malformedMessageIsDurablyQuarantinedBeforeAcknowledgement() {
        var runtime=new GenerationQueueRuntime(store,mock(GenerationTaskExecutor.class),config,mock(KafkaTemplate.class),
                mock(KafkaListenerEndpointRegistry.class),new SimpleMeterRegistry(),recovery);
        var record=new ConsumerRecord<String,String>("tasks",0,1,"1","{\"prompt\":\"do not persist this secret\"}");
        var ack=mock(Acknowledgment.class);
        doAnswer(call->{assertEquals(1,failures());return null;}).when(ack).acknowledge();
        runtime.consume(record,ack);runtime.consume(record,ack);
        assertEquals(1,failures());verify(ack,times(2)).acknowledge();
        assertEquals("invalid_message",jdbc.queryForObject("SELECT reason FROM generation_failure",String.class));
    }
    @Test void legacyInterruptedFailureReleasesAppWithoutWritingAnotherFailureHistory() {
        var task=task(1);store.claim(task.taskId(),"old");
        store.finish(task.taskId(),"INTERRUPTED","old restart",()->{});expire(task.taskId());status(task,"failed");
        recovery.recover();assertEquals("FAILED",store.get(task.taskId()).status());
        assertNotNull(store.submit(1,7,"another","html","new","trace",()->{}));
        verify(work,never()).completeHistory(any(),anyString(),any());
    }
    @Test void temporaryTaskFailureIsDurablyRetriedAndThenQuarantinedAtBudget() {
        config.setMaxRetries(1);var task=task(1);
        var executor=mock(GenerationTaskExecutor.class);
        var runtime=new GenerationQueueRuntime(store,executor,config,mock(KafkaTemplate.class),mock(KafkaListenerEndpointRegistry.class),new SimpleMeterRegistry(),recovery);
        doThrow(new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED)).when(executor).execute(task.taskId());
        var record=new ConsumerRecord<String,String>("tasks",0,1,"1","{\"version\":1,\"taskId\":\""+task.taskId()+"\"}");
        var ack=mock(Acknowledgment.class);runtime.consume(record,ack);
        assertEquals("QUEUED",store.get(task.taskId()).status());assertEquals(1,store.retries(task.taskId()));
        runtime.consume(record,ack);assertEquals("FAILED",store.get(task.taskId()).status());
        assertEquals(1,failures());verify(ack,times(2)).acknowledge();
    }
    @Test void unavailableQuarantineStorageNeverAcknowledgesMalformedMessage() {
        var unavailable=mock(GenerationTaskStore.class);
        doThrow(new DataAccessResourceFailureException("offline")).when(unavailable).quarantine(anyString(),isNull(),anyString());
        var runtime=new GenerationQueueRuntime(unavailable,mock(GenerationTaskExecutor.class),config,mock(KafkaTemplate.class),mock(KafkaListenerEndpointRegistry.class),new SimpleMeterRegistry(),recovery);
        var ack=mock(Acknowledgment.class);
        assertThrows(DataAccessResourceFailureException.class,()->runtime.consume(new ConsumerRecord<String,String>("tasks",0,1,"1","invalid"),ack));
        verifyNoInteractions(ack);
    }
    @Test void transientClaimedFailureWaitsForSafeCheckpointRecovery() {
        var task=task(1);when(work.stream(any())).thenReturn(Flux.error(new BusinessException(ErrorCode.PYTHON_SERVICE_TIMEOUT)));
        new GenerationTaskExecutor(store,work,config).execute(task.taskId());
        assertEquals("RUNNING",store.get(task.taskId()).status());assertFalse(store.owns(task.taskId(),store.get(task.taskId()).ownerId()));
        expire(task.taskId());status(task,"paused");recovery.recover();
        assertEquals("QUEUED",store.get(task.taskId()).status());assertTrue(store.shouldResume(task.taskId()));
        verify(work,never()).completeHistory(any(),anyString(),any());
    }
    @Test void disabledAutoRecoveryRetainsManualContinuePath() {
        config.setAutoRecoveryEnabled(false);var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());status(task,"interrupted");
        recovery.recover();recovery.recover();assertEquals("INTERRUPTED",store.get(task.taskId()).status());
        verify(work,times(1)).completeHistory(any(),eq("INTERRUPTED"),anyString());
        assertEquals("QUEUED",store.resume(task.taskId(),true).status());
    }
    @Test void localExecutionIsNeverTakenOverEvenAfterLeaseExpires() {
        var task=task(1);store.claim(task.taskId(),"old");expire(task.taskId());
        var executing=mock(GenerationTaskExecutor.class);when(executing.isExecuting(task.taskId())).thenReturn(true);
        new GenerationTaskRecovery(store,work,config,executing).recover();
        assertEquals("RUNNING",store.get(task.taskId()).status());verifyNoInteractions(work);
    }
}
