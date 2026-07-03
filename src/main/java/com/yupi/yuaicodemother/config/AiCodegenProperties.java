package com.yupi.yuaicodemother.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "ai.codegen")
public class AiCodegenProperties {

    private int maxConcurrentRequests = 8;
    private int permitLeaseMinutes = 30;
}
