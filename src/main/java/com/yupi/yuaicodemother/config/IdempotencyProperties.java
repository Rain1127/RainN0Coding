package com.yupi.yuaicodemother.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Data
@Component
@ConfigurationProperties(prefix = "idempotency")
public class IdempotencyProperties {

    private boolean enabled = true;
    private int processingTtlMinutes = 10;
    private int aiProcessingTtlMinutes = 30;
    private int successTtlHours = 24;
    private int failureTtlMinutes = 5;

    public Duration processingTtl() {
        return Duration.ofMinutes(processingTtlMinutes);
    }

    public Duration aiProcessingTtl() {
        return Duration.ofMinutes(aiProcessingTtlMinutes);
    }

    public Duration successTtl() {
        return Duration.ofHours(successTtlHours);
    }

    public Duration failureTtl() {
        return Duration.ofMinutes(failureTtlMinutes);
    }
}
