package com.yupi.yuaicodemother.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Data
@Component
@ConfigurationProperties(prefix = "python.ai")
public class PythonAiProperties {

    private String baseUrl = "http://localhost:8000";
    private String internalToken = "";
    private int connectTimeoutMs = 3000;
    private int responseTimeoutSeconds = 1800;
    private int routeTimeoutSeconds = 30;

    public Duration getConnectTimeout() {
        return Duration.ofMillis(connectTimeoutMs);
    }

    public Duration getResponseTimeout() {
        return Duration.ofSeconds(responseTimeoutSeconds);
    }

    public Duration getRouteTimeout() {
        return Duration.ofSeconds(routeTimeoutSeconds);
    }
}
