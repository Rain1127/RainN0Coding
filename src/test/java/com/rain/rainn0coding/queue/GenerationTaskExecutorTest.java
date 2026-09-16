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
        verify(store).append("id","{\"type\":\"progress\"}");
        verify(store,never()).append(eq("id"),contains("done"));
        verify(store).finish(eq("id"),eq("SUCCEEDED"),isNull(),any());
    }
    @Test void postDoneFailureNeverBecomesSuccess() {
        ready(Flux.concat(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"),Flux.error(new IllegalStateException("build failed"))));
        executor.execute("id");
        verify(store,never()).finish(anyString(),eq("SUCCEEDED"),any(),any());
        verify(store).finish(eq("id"),eq("FAILED"),anyString(),any());
    }
    @Test void missingSuccessfulDoneFailsClosed() {
        ready(Flux.just("{\"type\":\"progress\"}")); executor.execute("id");
        verify(store).finish(eq("id"),eq("FAILED"),anyString(),any());
    }
    @Test void semanticErrorCannotBeOverriddenBySuccessDone() {
        ready(Flux.just("{\"type\":\"error\",\"message\":\"rejected\"}","{\"type\":\"done\",\"status\":\"success\"}")); executor.execute("id");
        verify(store).finish(eq("id"),eq("FAILED"),eq("rejected"),any());
    }
    @Test void duplicateTerminalMessageNeverExecutesAgain() {
        when(store.get("id")).thenReturn(task("SUCCEEDED")); executor.execute("id"); verifyNoInteractions(work);
    }
    @Test void orphanedPythonExecutionPreventsNewClaim() {
        when(store.get("id")).thenReturn(task("QUEUED")); when(work.busy(1)).thenReturn(true);
        assertThrows(IllegalStateException.class,()->executor.execute("id"));
        verify(store,never()).claim(anyString(),anyString());
    }
}
