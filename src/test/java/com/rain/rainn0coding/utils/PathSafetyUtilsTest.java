package com.rain.rainn0coding.utils;

import com.rain.rainn0coding.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class PathSafetyUtilsTest {

    @TempDir
    Path tempDir;

    @Test
    void resolveInsideAllowsChildPath() {
        Path resolved = PathSafetyUtils.resolveInside(tempDir, "app", "index.html");

        assertEquals(tempDir.resolve("app").resolve("index.html").normalize(), resolved);
    }

    @Test
    void resolveInsideRejectsTraversal() {
        assertThrows(BusinessException.class,
                () -> PathSafetyUtils.resolveInside(tempDir, "app", "../secret.txt"));
    }

    @Test
    void resolveInsideRejectsSiblingPrefixEscape() {
        assertThrows(BusinessException.class,
                () -> PathSafetyUtils.resolveInside(tempDir.resolve("app"), "../app-other/secret.txt"));
    }
}
