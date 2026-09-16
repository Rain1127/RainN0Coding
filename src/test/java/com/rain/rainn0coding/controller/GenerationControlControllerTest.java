package com.rain.rainn0coding.controller;

import cn.hutool.json.JSONUtil;
import com.rain.rainn0coding.config.IdempotencyProperties;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.idempotency.IdempotencyDecision;
import com.rain.rainn0coding.idempotency.IdempotencyService;
import com.rain.rainn0coding.model.dto.app.GenerationControlRequest;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;

import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class GenerationControlControllerTest {
    private final AppController controller = new AppController();
    private final AppService service = mock(AppService.class);
    private final UserService users = mock(UserService.class);
    private final IdempotencyService idempotency = mock(IdempotencyService.class);
    private final HttpServletRequest request = mock(HttpServletRequest.class);
    private final User user = new User();

    @BeforeEach
    void setUp() {
        user.setId(7L);
        when(users.getLoginUser(request)).thenReturn(user);
        ReflectionTestUtils.setField(controller, "appService", service);
        ReflectionTestUtils.setField(controller, "userService", users);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotency);
        ReflectionTestUtils.setField(controller, "idempotencyProperties", new IdempotencyProperties());
    }

    @Test
    void pausedStreamDoesNotCompleteOrFailIdempotency() {
        when(idempotency.fingerprint("app:chat:gen-code", 12L, "hello")).thenReturn("fp");
        when(idempotency.start(eq("app:chat:gen-code"), eq(7L), eq("run"), eq("fp"), any()))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, "key", null));
        when(service.chatToGenCode(12L, "hello", user, "run", "run"))
                .thenReturn(Flux.just("data: {\"type\":\"done\",\"status\":\"paused\"}"));
        var events = controller.chatToGenCode(12L, "hello", "run", request).collectList().block();
        assertThat(events).hasSize(2);
        assertThat(JSONUtil.parseObj(events.getFirst().data()).getStr("d")).contains("paused");
        verify(idempotency, never()).markFailed(any(), any(), anyInt(), any());
        verify(idempotency, never()).markSuccess(any(), any(), any(), anyInt());
    }

    @Test
    void resumeBypassesOriginalIdempotencyAndUsesExistingEnvelope() {
        String chunk = "{\"type\":\"workflow_resumed\",\"request_id\":\"run\"}";
        when(service.resumeGeneration(12L, "run", user)).thenReturn(Flux.just(chunk));
        var events = controller.resumeGeneration(12L, "run", request).collectList().block();
        assertThat(JSONUtil.parseObj(events.getFirst().data()).getStr("d")).isEqualTo(chunk);
        assertThat(events.getLast().event()).isEqualTo("done");
        verifyNoInteractions(idempotency);
    }

    @Test
    void pauseAndStatusReturnControlResultForLoggedInUser() {
        Map<String, Object> result = Map.of("run_id", "run", "status", "paused");
        when(service.pauseGeneration(12L, "run", user)).thenReturn(result);
        when(service.generationStatus(12L, "run", user)).thenReturn(result);
        assertThat(controller.pauseGeneration(new GenerationControlRequest(12L, "run"), request).getData()).isEqualTo(result);
        assertThat(controller.generationStatus(12L, "run", request).getData()).isEqualTo(result);
    }

    @Test
    void allControlsRequireLogin() {
        when(users.getLoginUser(request)).thenThrow(new BusinessException(ErrorCode.NOT_LOGIN_ERROR));
        assertThatThrownBy(() -> controller.pauseGeneration(new GenerationControlRequest(12L, "run"), request))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> controller.generationStatus(12L, "run", request)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> controller.resumeGeneration(12L, "run", request)).isInstanceOf(BusinessException.class);
        verifyNoInteractions(service, idempotency);
    }
}
