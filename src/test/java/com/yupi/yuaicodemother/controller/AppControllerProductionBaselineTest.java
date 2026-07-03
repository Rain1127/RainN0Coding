package com.yupi.yuaicodemother.controller;

import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.common.BaseResponse;
import com.yupi.yuaicodemother.config.IdempotencyProperties;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.idempotency.IdempotencyDecision;
import com.yupi.yuaicodemother.idempotency.IdempotencyRecord;
import com.yupi.yuaicodemother.idempotency.IdempotencyService;
import com.yupi.yuaicodemother.model.dto.app.AppAddRequest;
import com.yupi.yuaicodemother.model.dto.app.AppDeployRequest;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.service.AppService;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AppControllerProductionBaselineTest {

    @Test
    void addAppReplaysSuccessfulIdempotentResponse() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:add", "build app")).thenReturn("fp");
        BaseResponse<Long> cached = new BaseResponse<>(0, 99L, "");
        IdempotencyRecord record = IdempotencyRecord.success("fp", JSONUtil.toJsonStr(cached), 200);
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_SUCCESS, "redis-key", record));

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");
        BaseResponse<Long> response = controller.addApp(body, "idem", request);

        assertThat(response.getData()).isEqualTo(99L);
        verify(appService, never()).createApp(any(), any());
    }

    @Test
    void addAppRejectsFingerprintConflict() {
        AppController controller = newController();
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:add", "build app")).thenReturn("fp");
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.FINGERPRINT_MISMATCH, "redis-key", null));

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");

        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.addApp(body, "idem", request));
        assertThat(exception.getCode()).isEqualTo(ErrorCode.REQUEST_REPLAY_CONFLICT.getCode());
    }

    @Test
    void addAppReplaysFailedIdempotentResponseWithoutCreatingApp() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:add", "build app")).thenReturn("fp");
        IdempotencyRecord record = IdempotencyRecord.failed("fp", ErrorCode.OPERATION_ERROR.getCode(), "previous failure");
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_FAILED, "redis-key", record));

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");

        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.addApp(body, "idem", request));

        assertThat(exception.getCode()).isEqualTo(ErrorCode.OPERATION_ERROR.getCode());
        assertThat(exception.getMessage()).isEqualTo("previous failure");
        verify(appService, never()).createApp(any(), any());
    }

    @Test
    void addAppMarksRuntimeExceptionAsSystemError() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:add", "build app")).thenReturn("fp");
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, "redis-key", null));
        RuntimeException failure = new RuntimeException("database unavailable");
        when(appService.createApp(any(), any())).thenThrow(failure);

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");

        assertThrows(RuntimeException.class, () -> controller.addApp(body, "idem", request));

        verify(idempotencyService).markFailed("redis-key", "fp",
                ErrorCode.SYSTEM_ERROR.getCode(), "database unavailable");
    }

    @Test
    void deployAppReplaysFailedIdempotentResponseWithoutDeploying() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:deploy", 12L)).thenReturn("fp");
        IdempotencyRecord record = IdempotencyRecord.failed("fp", ErrorCode.SYSTEM_ERROR.getCode(), "deploy failed");
        when(idempotencyService.start("app:deploy", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_FAILED, "redis-key", record));

        AppDeployRequest body = new AppDeployRequest();
        body.setAppId(12L);

        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.deployApp(body, "idem", request));

        assertThat(exception.getCode()).isEqualTo(ErrorCode.SYSTEM_ERROR.getCode());
        assertThat(exception.getMessage()).isEqualTo("deploy failed");
        verify(appService, never()).deployApp(any(), any());
    }

    @Test
    void deployAppMarksRuntimeExceptionAsSystemError() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:deploy", 12L)).thenReturn("fp");
        when(idempotencyService.start("app:deploy", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, "redis-key", null));
        when(appService.deployApp(eq(12L), eq(user))).thenThrow(new RuntimeException("copy failed"));

        AppDeployRequest body = new AppDeployRequest();
        body.setAppId(12L);

        assertThrows(RuntimeException.class, () -> controller.deployApp(body, "idem", request));

        verify(idempotencyService).markFailed("redis-key", "fp",
                ErrorCode.SYSTEM_ERROR.getCode(), "copy failed");
    }

    @Test
    void chatToGenCodeMarksSemanticOverloadAsFailed() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:chat:gen-code", 12L, "hello")).thenReturn("fp");
        when(idempotencyService.start("app:chat:gen-code", 1L, "idem", "fp", Duration.ofMinutes(30)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, "redis-key", null));
        when(appService.chatToGenCode(12L, "hello", user, "idem", "idem"))
                .thenReturn(Flux.just(
                        "{\"type\":\"error\",\"status\":\"overloaded\",\"message\":\"capacity full\"}",
                        "{\"type\":\"done\",\"status\":\"overloaded\"}"
                ));

        List<ServerSentEvent<String>> events = controller.chatToGenCode(12L, "hello", "idem", request)
                .collectList()
                .block();

        assertThat(events).hasSize(3);
        verify(idempotencyService).markFailed("redis-key", "fp",
                ErrorCode.AI_GENERATION_OVERLOADED.getCode(), "capacity full");
        verify(idempotencyService, never()).markSuccess(any(), any(), any(), any(Integer.class));
    }

    @Test
    void chatToGenCodeReplaysFailedIdempotentResponseWithoutGenerating() {
        AppController controller = newController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        IdempotencyProperties idempotencyProperties = new IdempotencyProperties();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", idempotencyProperties);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint("app:chat:gen-code", 12L, "hello")).thenReturn("fp");
        IdempotencyRecord record = IdempotencyRecord.failed("fp", ErrorCode.SYSTEM_ERROR.getCode(), "previous failure");
        when(idempotencyService.start("app:chat:gen-code", 1L, "idem", "fp", Duration.ofMinutes(30)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_FAILED, "redis-key", record));

        List<ServerSentEvent<String>> events = controller.chatToGenCode(12L, "hello", "idem", request)
                .collectList()
                .block();

        assertThat(events).hasSize(2);
        String payload = JSONUtil.parseObj(events.get(0).data()).getStr("d");
        assertThat(payload).contains("\"type\":\"error\"", "\"status\":\"failed\"", "previous failure");
        verify(appService, never()).chatToGenCode(any(), any(), any(), any(), any());
    }

    private AppController newController() {
        return new AppController();
    }
}
