package com.rain.rainn0coding.service.impl;

import com.rain.rainn0coding.concurrency.AiGenerationPermitService;
import com.rain.rainn0coding.core.AiCodeGeneratorFacade;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.monitor.TraceIdResolver;
import com.rain.rainn0coding.service.ChatHistoryService;
import org.junit.jupiter.api.Test;
import org.redisson.api.RLock;
import org.redisson.api.RFuture;
import org.redisson.api.RedissonClient;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AppServiceImplProductionBaselineTest {

    @Test
    void chatToGenCodeReturnsOverloadedEventsWhenPermitUnavailable() throws Exception {
        AppServiceImpl appService = spy(new AppServiceImpl());
        ChatHistoryService chatHistoryService = mock(ChatHistoryService.class);
        AiCodeGeneratorFacade aiCodeGeneratorFacade = mock(AiCodeGeneratorFacade.class);
        AiGenerationPermitService aiGenerationPermitService = mock(AiGenerationPermitService.class);
        RedissonClient redissonClient = mock(RedissonClient.class);
        RLock lock = mock(RLock.class);
        TraceIdResolver traceIdResolver = mock(TraceIdResolver.class);
        ReflectionTestUtils.setField(appService, "chatHistoryService", chatHistoryService);
        ReflectionTestUtils.setField(appService, "aiCodeGeneratorFacade", aiCodeGeneratorFacade);
        ReflectionTestUtils.setField(appService, "aiGenerationPermitService", aiGenerationPermitService);
        ReflectionTestUtils.setField(appService, "redissonClient", redissonClient);
        ReflectionTestUtils.setField(appService, "traceIdResolver", traceIdResolver);

        User user = new User();
        user.setId(7L);
        user.setUserRole("user");
        App app = new App();
        app.setId(12L);
        app.setUserId(7L);
        app.setCodeGenType("html");
        doReturn(app).when(appService).getById(12L);
        when(redissonClient.getLock("ai:chat:lock:12:7")).thenReturn(lock);
        when(lock.tryLock(0, TimeUnit.SECONDS)).thenReturn(true);
        @SuppressWarnings("unchecked")
        RFuture<Void> unlockFuture = mock(RFuture.class);
        when(lock.unlockAsync(Thread.currentThread().threadId())).thenReturn(unlockFuture);
        when(traceIdResolver.resolveCurrentTraceId()).thenReturn("trace-1");
        when(aiGenerationPermitService.tryAcquire()).thenReturn(AiGenerationPermitService.PermitHandle.notAcquired());

        List<String> events = appService.chatToGenCode(12L, "hello", user, "req-1", "idem-1")
                .collectList()
                .block();

        assertThat(events).containsExactly(
                "{\"type\":\"error\",\"status\":\"overloaded\",\"message\":\"AI generation capacity is full. Please retry later.\"}",
                "{\"type\":\"done\",\"status\":\"overloaded\"}"
        );
        verify(chatHistoryService).addChatMessage(eq(12L), eq("hello"), eq("user"), eq(7L));
        verify(chatHistoryService).addChatMessage(eq(12L), contains("繁忙"), eq("ai"), eq(7L));
        verify(aiCodeGeneratorFacade, never()).generateAndSaveCodeStream(any(), any(), any(), any(), any(), any(), any());
        verify(lock).unlockAsync(Thread.currentThread().threadId());
        verify(lock, never()).isHeldByCurrentThread();
    }

    @Test
    void chatToGenCodeReleasesPermitAfterStreamCompletes() throws Exception {
        AppServiceImpl appService = spy(new AppServiceImpl());
        ChatHistoryService chatHistoryService = mock(ChatHistoryService.class);
        AiCodeGeneratorFacade aiCodeGeneratorFacade = mock(AiCodeGeneratorFacade.class);
        AiGenerationPermitService aiGenerationPermitService = mock(AiGenerationPermitService.class);
        RedissonClient redissonClient = mock(RedissonClient.class);
        RLock lock = mock(RLock.class);
        TraceIdResolver traceIdResolver = mock(TraceIdResolver.class);
        ReflectionTestUtils.setField(appService, "chatHistoryService", chatHistoryService);
        ReflectionTestUtils.setField(appService, "aiCodeGeneratorFacade", aiCodeGeneratorFacade);
        ReflectionTestUtils.setField(appService, "aiGenerationPermitService", aiGenerationPermitService);
        ReflectionTestUtils.setField(appService, "redissonClient", redissonClient);
        ReflectionTestUtils.setField(appService, "traceIdResolver", traceIdResolver);

        User user = new User();
        user.setId(7L);
        user.setUserRole("user");
        App app = new App();
        app.setId(12L);
        app.setUserId(7L);
        app.setCodeGenType("html");
        AiGenerationPermitService.PermitHandle permit = new AiGenerationPermitService.PermitHandle(true, "permit-1");
        doReturn(app).when(appService).getById(12L);
        when(redissonClient.getLock("ai:chat:lock:12:7")).thenReturn(lock);
        when(lock.tryLock(0, TimeUnit.SECONDS)).thenReturn(true);
        @SuppressWarnings("unchecked")
        RFuture<Void> unlockFuture = mock(RFuture.class);
        when(lock.unlockAsync(Thread.currentThread().threadId())).thenReturn(unlockFuture);
        when(traceIdResolver.resolveCurrentTraceId()).thenReturn("trace-1");
        when(aiGenerationPermitService.tryAcquire()).thenReturn(permit);
        when(aiCodeGeneratorFacade.generateAndSaveCodeStream(
                eq("hello"), any(), eq(12L), eq(7L), eq("user"), eq("req-1"), eq("idem-1")))
                .thenReturn(Flux.just("data: {\"type\":\"done\"}"));

        List<String> events = appService.chatToGenCode(12L, "hello", user, "req-1", "idem-1")
                .collectList()
                .block();

        assertThat(events).containsExactly("data: {\"type\":\"done\"}");
        verify(aiGenerationPermitService).release(permit);
        verify(lock).unlockAsync(Thread.currentThread().threadId());
        verify(lock, never()).isHeldByCurrentThread();
    }

    @Test
    void chatToGenCodeDoesNotAcquireLockBeforeSubscription() {
        AppServiceImpl appService = spy(new AppServiceImpl());
        ChatHistoryService chatHistoryService = mock(ChatHistoryService.class);
        AiCodeGeneratorFacade aiCodeGeneratorFacade = mock(AiCodeGeneratorFacade.class);
        AiGenerationPermitService aiGenerationPermitService = mock(AiGenerationPermitService.class);
        RedissonClient redissonClient = mock(RedissonClient.class);
        ReflectionTestUtils.setField(appService, "chatHistoryService", chatHistoryService);
        ReflectionTestUtils.setField(appService, "aiCodeGeneratorFacade", aiCodeGeneratorFacade);
        ReflectionTestUtils.setField(appService, "aiGenerationPermitService", aiGenerationPermitService);
        ReflectionTestUtils.setField(appService, "redissonClient", redissonClient);

        User user = new User();
        user.setId(7L);

        appService.chatToGenCode(12L, "hello", user, "req-1", "idem-1");

        verifyNoInteractions(redissonClient, aiGenerationPermitService, aiCodeGeneratorFacade, chatHistoryService);
    }

    @Test
    void chatToGenCodeRecordsFailureHistoryWhenStreamEndsWithSemanticFailure() throws Exception {
        AppServiceImpl appService = spy(new AppServiceImpl());
        ChatHistoryService chatHistoryService = mock(ChatHistoryService.class);
        AiCodeGeneratorFacade aiCodeGeneratorFacade = mock(AiCodeGeneratorFacade.class);
        AiGenerationPermitService aiGenerationPermitService = mock(AiGenerationPermitService.class);
        RedissonClient redissonClient = mock(RedissonClient.class);
        RLock lock = mock(RLock.class);
        TraceIdResolver traceIdResolver = mock(TraceIdResolver.class);
        ReflectionTestUtils.setField(appService, "chatHistoryService", chatHistoryService);
        ReflectionTestUtils.setField(appService, "aiCodeGeneratorFacade", aiCodeGeneratorFacade);
        ReflectionTestUtils.setField(appService, "aiGenerationPermitService", aiGenerationPermitService);
        ReflectionTestUtils.setField(appService, "redissonClient", redissonClient);
        ReflectionTestUtils.setField(appService, "traceIdResolver", traceIdResolver);

        User user = new User();
        user.setId(7L);
        user.setUserRole("user");
        App app = new App();
        app.setId(12L);
        app.setUserId(7L);
        app.setCodeGenType("html");
        AiGenerationPermitService.PermitHandle permit = new AiGenerationPermitService.PermitHandle(true, "permit-1");
        doReturn(app).when(appService).getById(12L);
        when(redissonClient.getLock("ai:chat:lock:12:7")).thenReturn(lock);
        when(lock.tryLock(0, TimeUnit.SECONDS)).thenReturn(true);
        @SuppressWarnings("unchecked")
        RFuture<Void> unlockFuture = mock(RFuture.class);
        when(lock.unlockAsync(Thread.currentThread().threadId())).thenReturn(unlockFuture);
        when(traceIdResolver.resolveCurrentTraceId()).thenReturn("trace-1");
        when(aiGenerationPermitService.tryAcquire()).thenReturn(permit);
        when(aiCodeGeneratorFacade.generateAndSaveCodeStream(
                eq("hello"), any(), eq(12L), eq(7L), eq("user"), eq("req-1"), eq("idem-1")))
                .thenReturn(Flux.just("data: {\"type\":\"done\",\"status\":\"error\"}"));

        List<String> events = appService.chatToGenCode(12L, "hello", user, "req-1", "idem-1")
                .collectList()
                .block();

        assertThat(events).containsExactly("data: {\"type\":\"done\",\"status\":\"error\"}");
        verify(chatHistoryService).addChatMessage(eq(12L), eq("hello"), eq("user"), eq(7L));
        verify(chatHistoryService).addChatMessage(eq(12L), contains("失败"), eq("ai"), eq(7L));
        verify(chatHistoryService, never()).addChatMessage(eq(12L), contains("完成"), eq("ai"), eq(7L));
    }
}
