package com.rain.rainn0coding.utils;

import com.rain.rainn0coding.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.withSettings;

class WebScreenshotUtilsTest {

    @Test
    void blankUrlDoesNotCreateDriver() {
        AtomicBoolean created = new AtomicBoolean();

        String result = WebScreenshotUtils.saveWebPageScreenshot(" ", () -> {
            created.set(true);
            return mock(WebDriver.class);
        });

        assertNull(result);
        assertFalse(created.get());
    }

    @Test
    void closesDriverWhenCaptureFails() {
        WebDriver driver = mock(WebDriver.class);
        doThrow(new RuntimeException("navigation failed"))
                .when(driver).get("https://example.test");

        String result = WebScreenshotUtils.saveWebPageScreenshot(
                "https://example.test", () -> driver);

        assertNull(result);
        verify(driver).quit();
    }

    @Test
    void restoresInterruptFlagWhenPageWaitIsInterrupted() {
        WebDriver driver = mock(
                WebDriver.class,
                withSettings().extraInterfaces(JavascriptExecutor.class));
        when(((JavascriptExecutor) driver).executeScript("return document.readyState"))
                .thenReturn("complete");
        Thread.currentThread().interrupt();

        try {
            assertThrows(
                    BusinessException.class,
                    () -> WebScreenshotUtils.waitForPageLoad(driver));
            assertTrue(Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted();
        }
    }
}
