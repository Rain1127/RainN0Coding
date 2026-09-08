package com.rain.rainn0coding.core.builder;

import cn.hutool.core.util.RuntimeUtil;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
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
        try (var runtime = mockStatic(RuntimeUtil.class)) {
            runtime.when(() -> RuntimeUtil.exec(isNull(), any(File.class), any(String[].class)))
                    .thenAnswer(call -> {
                        commands.add(List.of((String[]) call.getRawArguments()[2]));
                        return process;
                    });
            assertThat(new VueProjectBuilder().buildProject(directory.toString())).isTrue();
        }
        assertThat(commands).hasSize(2);
        assertThat(commands.get(1).subList(1, commands.get(1).size()))
                .containsExactly("run", "build", "--", "--base=./");
    }
}
