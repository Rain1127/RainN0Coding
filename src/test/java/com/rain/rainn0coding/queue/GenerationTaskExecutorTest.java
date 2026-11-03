package com.rain.rainn0coding.queue;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import java.time.Instant;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class GenerationTaskExecutorTest {
    final GenerationTaskStore store=mock(GenerationTaskStore.class);
    final GenerationWork work=mock(GenerationWork.class);
    final GenerationQueueProperties config=new GenerationQueueProperties();
    final GenerationTaskExecutor executor=new GenerationTaskExecutor(store,work,config);
    GenerationTaskStore.Task task(String state) {
        return new GenerationTaskStore.Task("id",1,2,"prompt","html","key","trace",state,null,0,Instant.now(),null);
    }
    void ready(Flux<String> stream) {
        when(store.get("id")).thenReturn(task("QUEUED"));
        when(store.claim(eq("id"),anyString())).thenReturn(true);
        when(work.stream(any())).thenReturn(stream);
    }
    @Test void doneIsNotPublishedUntilStreamAndFinalizationComplete() {
        ready(Flux.just("{\"type\":\"progress\"}","{\"type\":\"done\",\"status\":\"success\"}"));
        executor.execute("id");
        verify(store).appendOwned(eq("id"),anyString(),eq("{\"type\":\"progress\"}"));
        verify(store,never()).appendOwned(eq("id"),anyString(),contains("done"));
        verify(store).finishOwned(eq("id"),anyString(),eq("SUCCEEDED"),isNull(),any());
    }
    @Test void postDoneFailureNeverBecomesSuccess() {
        ready(Flux.concat(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"),Flux.error(new IllegalStateException("build failed"))));
        executor.execute("id");
        verify(store,never()).finishOwned(anyString(),anyString(),eq("SUCCEEDED"),any(),any());
        verify(store).finishOwned(eq("id"),anyString(),eq("FAILED"),anyString(),any());
    }
    @Test void missingSuccessfulDoneFailsClosed() {
        ready(Flux.just("{\"type\":\"progress\"}")); executor.execute("id");
        verify(store).finishOwned(eq("id"),anyString(),eq("FAILED"),anyString(),any());
    }
    @Test void semanticErrorCannotBeOverriddenBySuccessDone() {
        ready(Flux.just("{\"type\":\"error\",\"message\":\"rejected\"}","{\"type\":\"done\",\"status\":\"success\"}")); executor.execute("id");
        verify(store).finishOwned(eq("id"),anyString(),eq("FAILED"),eq("rejected"),any());
    }
    @Test void duplicateTerminalMessageNeverExecutesAgain() {
        when(store.get("id")).thenReturn(task("SUCCEEDED")); executor.execute("id"); verifyNoInteractions(work);
    }
    @Test void orphanedPythonExecutionPreventsNewClaim() {
        when(store.get("id")).thenReturn(task("QUEUED")); when(work.busy(1)).thenReturn(true);
        executor.execute("id");
        verify(store).delayQueued(eq("id"),eq(false),any());
        verify(store,never()).claim(anyString(),anyString());
    }
    @Test void pausedCheckpointIsNotSuccessOrFailureAndDoesNotWriteCompletionHistory() {
        ready(Flux.just("{\"type\":\"done\",\"status\":\"paused\"}"));executor.execute("id");
        verify(store).pauseOwned(eq("id"),anyString());
        verify(store,never()).finishOwned(anyString(),anyString(),anyString(),any(),any());
        verify(work,never()).completeHistory(any(),anyString(),any());
    }
    @Test void pausedDuplicateDoesNotResumeWithoutExplicitUserRequest() {
        when(store.get("id")).thenReturn(task("PAUSED"));executor.execute("id");verifyNoInteractions(work);
    }
}
