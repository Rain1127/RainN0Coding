package com.yupi.yuaicodemother.core.saver;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertThrows;

class LegacyCodeSaverCleanupTest {

    @Test
    void codeFileSaverExecutorShouldBeRemoved() {
        assertThrows(ClassNotFoundException.class,
                () -> Class.forName("com.yupi.yuaicodemother.core.saver.CodeFileSaverExecutor"));
    }

    @Test
    void legacySaverClassesShouldBeRemoved() {
        List<String> legacyClasses = List.of(
                "com.yupi.yuaicodemother.ai.model.HtmlCodeResult",
                "com.yupi.yuaicodemother.ai.model.MultiFileCodeResult",
                "com.yupi.yuaicodemother.core.saver.CodeFileSaverTemplate",
                "com.yupi.yuaicodemother.core.saver.HtmlCodeFileSaverTemplate",
                "com.yupi.yuaicodemother.core.saver.MultiFileCodeFileSaverTemplate"
        );

        for (String className : legacyClasses) {
            assertThrows(ClassNotFoundException.class, () -> Class.forName(className), className);
        }
    }
}
