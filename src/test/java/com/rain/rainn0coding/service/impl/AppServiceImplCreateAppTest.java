package com.rain.rainn0coding.service.impl;

import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.model.dto.app.AppAddRequest;
import com.rain.rainn0coding.model.entity.App;
import com.rain.rainn0coding.model.entity.User;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AppServiceImplCreateAppTest {

    @Test
    void shouldCreateAppUsingPythonRoutedCodeGenType() {
        AppServiceImpl appService = spy(new AppServiceImpl());
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        ReflectionTestUtils.setField(appService, "pythonAiClient", pythonAiClient);

        when(pythonAiClient.routeCodeGenType("simple login page")).thenReturn("html");
        doAnswer(invocation -> {
            App app = invocation.getArgument(0);
            app.setId(123L);
            return true;
        }).when(appService).save(any(App.class));

        AppAddRequest request = new AppAddRequest();
        request.setInitPrompt("simple login page");
        User loginUser = new User();
        loginUser.setId(99L);

        Long appId = appService.createApp(request, loginUser);

        ArgumentCaptor<App> appCaptor = ArgumentCaptor.forClass(App.class);
        verify(appService).save(appCaptor.capture());
        App savedApp = appCaptor.getValue();
        assertEquals(123L, appId);
        assertEquals("html", savedApp.getCodeGenType());
        assertEquals(99L, savedApp.getUserId());
        assertTrue(savedApp.getAppName().startsWith("simple login"));
    }

    @Test
    void shouldFallbackToVueProjectWhenPythonReturnsUnsupportedCodeGenType() {
        AppServiceImpl appService = spy(new AppServiceImpl());
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        ReflectionTestUtils.setField(appService, "pythonAiClient", pythonAiClient);

        when(pythonAiClient.routeCodeGenType("admin dashboard")).thenReturn("desktop_app");
        doAnswer(invocation -> {
            App app = invocation.getArgument(0);
            app.setId(456L);
            return true;
        }).when(appService).save(any(App.class));

        AppAddRequest request = new AppAddRequest();
        request.setInitPrompt("admin dashboard");
        User loginUser = new User();
        loginUser.setId(88L);

        appService.createApp(request, loginUser);

        ArgumentCaptor<App> appCaptor = ArgumentCaptor.forClass(App.class);
        verify(appService).save(appCaptor.capture());
        assertEquals("vue_project", appCaptor.getValue().getCodeGenType());
    }

    @Test
    void shouldFallbackToVueProjectWhenPythonRoutingFails() {
        AppServiceImpl appService = spy(new AppServiceImpl());
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        ReflectionTestUtils.setField(appService, "pythonAiClient", pythonAiClient);

        when(pythonAiClient.routeCodeGenType("shopping app")).thenThrow(new RuntimeException("python down"));
        doAnswer(invocation -> {
            App app = invocation.getArgument(0);
            app.setId(789L);
            return true;
        }).when(appService).save(any(App.class));

        AppAddRequest request = new AppAddRequest();
        request.setInitPrompt("shopping app");
        User loginUser = new User();
        loginUser.setId(77L);

        appService.createApp(request, loginUser);

        ArgumentCaptor<App> appCaptor = ArgumentCaptor.forClass(App.class);
        verify(appService).save(appCaptor.capture());
        assertEquals("vue_project", appCaptor.getValue().getCodeGenType());
    }
}
