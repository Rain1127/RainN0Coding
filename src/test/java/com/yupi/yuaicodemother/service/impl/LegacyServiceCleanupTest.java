package com.yupi.yuaicodemother.service.impl;

import com.yupi.yuaicodemother.service.AppService;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LegacyServiceCleanupTest {

    @Test
    void screenshotAsyncHelperShouldNotBeExposedFromAppService() throws Exception {
        assertFalse(hasMethod(AppService.class, "generateAppScreenshotAsync", Long.class, String.class));

        Method method = AppServiceImpl.class.getDeclaredMethod("generateAppScreenshotAsync", Long.class, String.class);
        assertTrue(Modifier.isPrivate(method.getModifiers()));
    }

    private static boolean hasMethod(Class<?> type, String methodName, Class<?>... parameterTypes) {
        return Arrays.stream(type.getDeclaredMethods())
                .anyMatch(method -> method.getName().equals(methodName)
                        && Arrays.equals(method.getParameterTypes(), parameterTypes));
    }
}
