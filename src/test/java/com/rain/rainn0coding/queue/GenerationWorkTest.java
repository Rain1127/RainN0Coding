package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.ChatHistoryService;
import com.rain.rainn0coding.service.UserService;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import java.time.Instant;
import java.util.function.BooleanSupplier;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class GenerationWorkTest {
    final AiCodeGeneratorFacade facade=mock(AiCodeGeneratorFacade.class);
    final GenerationTaskStore store=mock(GenerationTaskStore.class);
    final AppService apps=mock(AppService.class);
    final UserService users=mock(UserService.class);
    final GenerationWork work=new GenerationWork(facade,mock(PythonAiClient.class),apps,users,mock(ChatHistoryService.class),store);
    final GenerationTaskStore.Task task=new GenerationTaskStore.Task("t",1,2,"prompt","html","key","trace","RUNNING",null,0,Instant.now(),"owner");
    void ready(Flux<String> events) {
        var app=new App();app.setUserId(2L);when(apps.getById(1L)).thenReturn(app);
        when(users.getById(2L)).thenReturn(User.builder().id(2L).userRole("user").build());
        when(facade.generateAndSaveCodeStream(anyString(),any(),anyLong(),anyLong(),anyString(),anyString(),anyString(),anyBoolean(),eq(true),any(BooleanSupplier.class)))
                .thenReturn(events);
    }
    @Test void onlySuccessfulFinalizationIsRecordedForReplay() {
        ready(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"));work.stream(task).blockLast();
        verify(store).markFinalized("t","owner");
    }
    @Test void pausedOrSemanticallyFailedStreamCannotSkipFutureGeneration() {
        ready(Flux.just("{\"type\":\"done\",\"status\":\"paused\"}"));work.stream(task).blockLast();
        ready(Flux.just("{\"type\":\"error\"}","{\"type\":\"done\",\"status\":\"success\"}"));work.stream(task).blockLast();
        verify(store,never()).markFinalized(anyString(),anyString());
    }
    @Test void recordedFinalizationSkipsModelFileWritesAndBuildOnRedelivery() {
        ready(Flux.error(new AssertionError("must not call pipeline")));
        when(store.finalized("t")).thenReturn(true);
        assertTrue(work.stream(task).blockLast().contains("success"));verifyNoInteractions(facade);
    }
    @Test void postDoneSaveFailureDoesNotRecordFinalization() {
        ready(Flux.concat(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"),Flux.error(new IllegalStateException("save"))));
        assertThrows(IllegalStateException.class,()->work.stream(task).blockLast());
        verify(store,never()).markFinalized(anyString(),anyString());
    }
}
