package com.rain.rainn0coding.service.impl;

import com.rain.rainn0coding.concurrency.AiGenerationPermitService;
import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import com.rain.rainn0coding.monitor.TraceIdResolver;
import com.rain.rainn0coding.service.ChatHistoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class GenerationPauseResumeTest {
    private final AppServiceImpl service = spy(new AppServiceImpl());
    private final PythonAiClient python = mock(PythonAiClient.class);
    private final AiCodeGeneratorFacade facade = mock(AiCodeGeneratorFacade.class);
    private final ChatHistoryService history = mock(ChatHistoryService.class);
    private final AiGenerationPermitService permits = mock(AiGenerationPermitService.class);
    private final RedissonClient redis = mock(RedissonClient.class);
    private final RLock lock = mock(RLock.class);
    private final User user = new User();
    private final App app = new App();
    private final AiGenerationPermitService.PermitHandle permit =
            new AiGenerationPermitService.PermitHandle(true, "permit");

    @BeforeEach
    void setUp() throws Exception {
        user.setId(7L);
        user.setUserRole("user");
        app.setId(12L);
        app.setUserId(7L);
        app.setCodeGenType("html");
        doReturn(app).when(service).getById(12L);
        ReflectionTestUtils.setField(service, "pythonAiClient", python);
        ReflectionTestUtils.setField(service, "aiCodeGeneratorFacade", facade);
        ReflectionTestUtils.setField(service, "chatHistoryService", history);
        ReflectionTestUtils.setField(service, "aiGenerationPermitService", permits);
        ReflectionTestUtils.setField(service, "redissonClient", redis);
        TraceIdResolver trace = mock(TraceIdResolver.class);
        when(trace.resolveCurrentTraceId()).thenReturn("trace");
        ReflectionTestUtils.setField(service, "traceIdResolver", trace);
        when(redis.getLock("ai:chat:lock:12:7")).thenReturn(lock);
        when(lock.tryLock(0, TimeUnit.SECONDS)).thenReturn(true);
        when(permits.tryAcquire()).thenReturn(permit);
    }

    @Test
    void controlsRejectOtherOwnersBeforePythonOrGenerationLock() {
        app.setUserId(8L);
        assertThatThrownBy(() -> service.pauseGeneration(12L, "run", user))
                .isInstanceOf(BusinessException.class).extracting("code").isEqualTo(ErrorCode.NO_AUTH_ERROR.getCode());
        assertThatThrownBy(() -> service.generationStatus(12L, "run", user)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.resumeGeneration(12L, "run", user)).isInstanceOf(BusinessException.class);
        verifyNoInteractions(python, redis, facade, history);
    }

    @Test
    void controlsForwardAuthenticatedOwnerAndOriginalRun() {
        when(python.pauseGeneration("7", "12", "run")).thenReturn(Map.of("run_id", "run", "status", "pausing"));
        when(python.generationStatus("7", "12", "run")).thenReturn(Map.of("run_id", "run", "status", "paused"));
        assertThat(service.pauseGeneration(12L, "run", user)).containsEntry("status", "pausing");
        assertThat(service.generationStatus(12L, "run", user)).containsEntry("status", "paused");
        verifyNoInteractions(redis, history, facade);
    }

    @Test
    void pauseKeepsPermitUntilStreamCompletesAndAddsNoSuccessOrFailureHistory() {
        Sinks.Many<String> events = Sinks.many().unicast().onBackpressureBuffer();
        when(facade.generateAndSaveCodeStream("hello", CodeGenTypeEnum.HTML, 12L, 7L, "user", "run", "run"))
                .thenReturn(events.asFlux());
        var subscription = service.chatToGenCode(12L, "hello", user, "run", "run").subscribe();
        events.tryEmitNext("data: {\"type\":\"paused\",\"request_id\":\"run\"}");
        events.tryEmitNext("data: {\"type\":\"done\",\"status\":\"paused\"}");
        verify(permits, never()).release(any());
        verify(lock, never()).unlockAsync(anyLong());
        events.tryEmitComplete();
        verify(permits).release(permit);
        verify(lock).unlockAsync(Thread.currentThread().threadId());
        verify(history).addChatMessage(12L, "hello", "user", 7L);
        verify(history, never()).addChatMessage(any(), any(), eq("ai"), any());
        subscription.dispose();
    }

    @Test
    void resumeUsesOriginalPipelineWithoutDuplicatingUserHistory() {
        when(facade.generateAndSaveCodeStream("", CodeGenTypeEnum.HTML, 12L, 7L, "user", "run", null, true))
                .thenReturn(Flux.just("{\"type\":\"done\",\"status\":\"success\"}"));
        assertThat(service.resumeGeneration(12L, "run", user).collectList().block()).hasSize(1);
        verify(history, never()).addChatMessage(any(), any(), eq("user"), any());
        verify(history).addChatMessage(eq(12L), contains("完成"), eq("ai"), eq(7L));
        verify(permits).release(permit);
        verify(lock).unlockAsync(Thread.currentThread().threadId());
    }

    @Test
    void simultaneousResumeIsRejectedByGenerationLock() throws Exception {
        when(lock.tryLock(0, TimeUnit.SECONDS)).thenReturn(false);
        assertThatThrownBy(() -> service.resumeGeneration(12L, "run", user).collectList().block())
                .isInstanceOf(BusinessException.class).extracting("code").isEqualTo(ErrorCode.CHAT_IN_PROGRESS.getCode());
        verifyNoInteractions(facade, history, permits);
    }
}
