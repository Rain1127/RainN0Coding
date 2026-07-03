package com.yupi.yuaicodemother.monitor;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class MonitoringScriptsTest {

    @Test
    void startMonitoringBatUsesRepositoryRootForComposeAndPrometheusFiles() throws IOException {
        Path script = Path.of("guide", "start-monitoring.bat");
        String content = Files.readString(script);

        assertThat(content).contains("%REPO_ROOT%\\docker-compose.monitoring.yml");
        assertThat(content).contains("%REPO_ROOT%\\prometheus.yml");
    }
}
