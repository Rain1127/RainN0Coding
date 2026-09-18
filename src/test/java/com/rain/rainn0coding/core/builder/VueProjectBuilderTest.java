package com.rain.rainn0coding.core.builder;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class VueProjectBuilderTest {
    @TempDir Path directory;

    @Test
    void buildsAssetsRelativeToPublishedSubdirectory() throws Exception {
        Files.writeString(directory.resolve("package.json"), "{}");
        Files.createDirectory(directory.resolve("dist"));
        Process process = mock(Process.class);
        when(process.waitFor(anyLong(), any(TimeUnit.class))).thenReturn(true);
        when(process.exitValue()).thenReturn(0);
        List<List<String>> commands = new ArrayList<>();
        try (var builders = mockConstruction(ProcessBuilder.class, (builder, context) -> {
            commands.add(List.of((String[]) context.arguments().getFirst()));
            when(builder.directory(any())).thenReturn(builder);
            when(builder.redirectErrorStream(true)).thenReturn(builder);
            when(builder.redirectOutput(any(ProcessBuilder.Redirect.class))).thenReturn(builder);
            when(builder.start()).thenReturn(process);
        })) {
            assertThat(new VueProjectBuilder().buildProject(directory.toString())).isTrue();
        }
        assertThat(commands).hasSize(2);
        assertThat(commands.get(1).subList(1, commands.get(1).size()))
                .containsExactly("run", "build", "--", "--base=./");
    }
}
