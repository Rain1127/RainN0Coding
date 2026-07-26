package com.rain.rainn0coding.config;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class LegacyLauncherCompatibilityTest {

    @Test
    void legacyIdeaRunConfigurationMainClassStillExists() throws Exception {
        Class<?> launcherClass = Class.forName("com.yupi.yuaicodemother.YuAiCodeMotherApplication");
        Method mainMethod = launcherClass.getMethod("main", String[].class);
        assertNotNull(mainMethod);
    }
}
