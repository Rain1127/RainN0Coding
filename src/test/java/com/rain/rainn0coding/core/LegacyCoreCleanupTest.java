package com.rain.rainn0coding.core;

import com.rain.rainn0coding.core.builder.VueProjectBuilder;
import com.rain.rainn0coding.core.python.PythonAiClient;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LegacyCoreCleanupTest {

    @Test
    void legacyCoreCompatibilityMethodsShouldBeRemoved() {
        assertFalse(hasMethod(AiCodeGeneratorFacade.class, "generateAndSaveCode", String.class,
                com.rain.rainn0coding.model.enums.CodeGenTypeEnum.class, Long.class));
        assertFalse(hasMethod(VueProjectBuilder.class, "buildProjectAsync", String.class));
        assertFalse(hasMethod(PythonAiClient.class, "healthCheck"));
    }

    @Test
    void legacyRoutingAdapterShouldBeRemoved() {
        assertThrows(ClassNotFoundException.class,
                () -> Class.forName("com.rain.rainn0coding.core.python.PythonCodeGenTypeRoutingService"));
    }

    private static boolean hasMethod(Class<?> type, String methodName, Class<?>... parameterTypes) {
        return Arrays.stream(type.getDeclaredMethods())
                .map(Method::toString)
                .anyMatch(signature -> signature.contains(type.getName() + "." + methodName + "(")
                        && matchesParameterTypes(type, methodName, parameterTypes));
    }

    private static boolean matchesParameterTypes(Class<?> type, String methodName, Class<?>... parameterTypes) {
        try {
            type.getDeclaredMethod(methodName, parameterTypes);
            return true;
        } catch (NoSuchMethodException e) {
            return false;
        }
    }
}
