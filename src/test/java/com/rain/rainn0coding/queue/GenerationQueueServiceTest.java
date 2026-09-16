package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.ChatHistoryService;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.time.Duration;
import java.util.List;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class GenerationQueueServiceTest {
    final GenerationTaskStore store=mock(GenerationTaskStore.class);
    final AppService apps=mock(AppService.class);
    final GenerationWork work=mock(GenerationWork.class);
    final GenerationQueueService service=new GenerationQueueService(store,new GenerationQueueProperties(),apps,mock(ChatHistoryService.class),work);
    final User user=User.builder().id(2L).build();
    GenerationTaskStore.Task task(String status) {return new GenerationTaskStore.Task("t",1,2,"secret","html","key","trace",status,null,3,Instant.now(),null);}
    void owned() {var app=new App();app.setId(1L);app.setUserId(2L);when(apps.getById(1L)).thenReturn(app);}
    @Test void anotherUserCannotReadOrSubscribe() {
        when(store.get("t")).thenReturn(task("RUNNING"));
        var other=User.builder().id(9L).build();
        assertThrows(RuntimeException.class,()->service.get("t",other));
        assertThrows(RuntimeException.class,()->service.events("t",0,other));
        verifyNoInteractions(work);
    }
    @Test void terminalReplayNeverExecutesOrSavesCodeAgain() {
        owned();when(store.get("t")).thenReturn(task("SUCCEEDED"));
        when(store.events("t",0)).thenReturn(List.of(new GenerationTaskStore.Event(3,"{\"type\":\"done\",\"status\":\"success\"}")));
        assertEquals(1,service.events("t",0,user).collectList().block(Duration.ofSeconds(3)).size());
        assertEquals(1,service.events("t",0,user).collectList().block(Duration.ofSeconds(3)).size());
        verifyNoInteractions(work);
        verify(store,never()).claim(anyString(),anyString());
    }
    @Test void expiredEventsStillReturnDurableTerminalStatus() {
        owned();when(store.get("t")).thenReturn(task("SUCCEEDED"));when(store.events("t",0)).thenReturn(List.of());
        var events=service.events("t",0,user).collectList().block(Duration.ofSeconds(3));
        assertTrue(events.getFirst().data().contains("success"));
    }
    @Test void interruptedTaskRetryIsDisabledWhenPythonIsUnavailable() {
        owned();when(store.get("t")).thenReturn(task("INTERRUPTED"));when(work.busy(1)).thenThrow(new IllegalStateException());
        assertFalse(service.get("t",user).retryAllowed());
    }
}
