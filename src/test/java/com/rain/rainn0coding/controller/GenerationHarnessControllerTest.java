package com.rain.rainn0coding.controller;

import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class GenerationHarnessControllerTest {
    @Test void preventsCrossOwnerEvidenceAccess() {
        var apps = mock(AppService.class);
        var users = mock(UserService.class);
        var python = mock(PythonAiClient.class);
        var request = mock(HttpServletRequest.class);
        var user = new User(); user.setId(1L);
        var app = new App(); app.setId(10L); app.setUserId(2L);
        when(users.getLoginUser(request)).thenReturn(user);
        when(apps.getById(10L)).thenReturn(app);
        var controller = new GenerationHarnessController(apps, users, python);
        assertThrows(BusinessException.class, () -> controller.steps(10L, "run", 0, 100, request));
        verifyNoInteractions(python);
    }

    @Test void forwardsAuthenticatedIdentityAndSeparateStepCursor() {
        var apps = mock(AppService.class);
        var users = mock(UserService.class);
        var python = mock(PythonAiClient.class);
        var request = mock(HttpServletRequest.class);
        var user = new User(); user.setId(1L);
        var app = new App(); app.setId(10L); app.setUserId(1L);
        when(users.getLoginUser(request)).thenReturn(user);
        when(apps.getById(10L)).thenReturn(app);
        when(python.generationEvents("1", "10", "run", 123L, 100)).thenReturn(Map.of("step_cursor", 124));
        var controller = new GenerationHarnessController(apps, users, python);
        assertEquals(124, controller.steps(10L, "run", 123L, 100, request).getData().get("step_cursor"));
        assertThrows(BusinessException.class, () -> controller.steps(10L, "run", -1, 100, request));
    }
}
