package com.rain.rainn0coding.core.saver;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertThrows;

class LegacyCodeSaverCleanupTest {

    @Test
    void codeFileSaverExecutorShouldBeRemoved() {
        assertThrows(ClassNotFoundException.class,
                () -> Class.forName("com.rain.rainn0coding.core.saver.CodeFileSaverExecutor"));
    }

    @Test
    void legacySaverClassesShouldBeRemoved() {
        List<String> legacyClasses = List.of(
                "com.rain.rainn0coding.ai.model.HtmlCodeResult",
                "com.rain.rainn0coding.ai.model.MultiFileCodeResult",
                "com.rain.rainn0coding.core.saver.CodeFileSaverTemplate",
                "com.rain.rainn0coding.core.saver.HtmlCodeFileSaverTemplate",
                "com.rain.rainn0coding.core.saver.MultiFileCodeFileSaverTemplate"
        );

        for (String className : legacyClasses) {
            assertThrows(ClassNotFoundException.class, () -> Class.forName(className), className);
        }
    }
}
