package com.rain.rainn0coding.core.builder;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import java.io.File;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class VueProjectBuilderCancellationTest {
    @Test void interruptedBuildKillsChildrenBeforeReleasingExecutionSlot() throws Exception {
        Process process=mock(Process.class);
        ProcessHandle child=mock(ProcessHandle.class);
        when(process.waitFor(anyLong(),any(TimeUnit.class))).thenThrow(new InterruptedException());
        when(process.isAlive()).thenReturn(true);
        when(process.descendants()).thenReturn(Stream.of(child));
        try(var construction=mockConstruction(ProcessBuilder.class,(builder,context)->{
            when(builder.directory(any())).thenReturn(builder);
            when(builder.redirectErrorStream(anyBoolean())).thenReturn(builder);
            when(builder.redirectOutput(any(ProcessBuilder.Redirect.class))).thenReturn(builder);
            when(builder.start()).thenReturn(process);
        })) {
            assertFalse(Boolean.TRUE.equals(ReflectionTestUtils.invokeMethod(new VueProjectBuilder(),"executeCommand",new File("."),"npm run build",180)));
            verify(child).destroyForcibly();verify(process).destroyForcibly();
            assertTrue(Thread.currentThread().isInterrupted());
        } finally {Thread.interrupted();}
    }
}
