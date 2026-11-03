package com.rain.rainn0coding.queue;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "app.generation-queue")
public class GenerationQueueProperties {
    private boolean enabled = false;
    private String bootstrapServers = "127.0.0.1:9092";
    private String topic = "rain-code-generation-v1";
    private String groupId = "rain-code-generation-workers-v1";
    private int maxPending = 100;
    private int maxWaitHours = 24;
    private int taskTimeoutMinutes = 30;
    private int eventRetentionDays = 7;
    private int maxPromptCharacters = 20000;
    private int maxEventsPerTask = 10000;
    private int maxEventBytes = 2 * 1024 * 1024;
    private boolean autoRecoveryEnabled = true;
    private int maxRetries = 3;
    private int retryBaseSeconds = 5;
    private int retryMaxSeconds = 60;
    private int heartbeatSeconds = 10;
    private int leaseSeconds = 60;

    public void validate() {
        if (maxPending < 1 || taskTimeoutMinutes < 1 || maxWaitHours < 1 || maxRetries < 0
                || retryBaseSeconds < 1 || retryMaxSeconds < retryBaseSeconds
                || heartbeatSeconds < 1 || leaseSeconds < 3L * heartbeatSeconds)
            throw new IllegalArgumentException("Invalid generation queue limits");
    }
}
