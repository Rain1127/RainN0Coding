package com.rain.rainn0coding.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionBaselinePropertiesTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(PropertiesBindingConfig.class);

    @Test
    void bindsPythonAiPropertiesFromConfiguredPrefix() {
        contextRunner
                .withPropertyValues(
                        "python.ai.base-url=http://python:8000",
                        "python.ai.internal-token=secret",
                        "python.ai.connect-timeout-ms=2500",
                        "python.ai.response-timeout-seconds=120",
                        "python.ai.route-timeout-seconds=5"
                )
                .run(context -> {
                    PythonAiProperties properties = context.getBean(PythonAiProperties.class);

                    assertThat(properties.getBaseUrl()).isEqualTo("http://python:8000");
                    assertThat(properties.getInternalToken()).isEqualTo("secret");
                    assertThat(properties.getConnectTimeout()).isEqualTo(Duration.ofMillis(2500));
                    assertThat(properties.getResponseTimeout()).isEqualTo(Duration.ofSeconds(120));
                    assertThat(properties.getRouteTimeout()).isEqualTo(Duration.ofSeconds(5));
                });
    }

    @Test
    void bindsAiCodegenPropertiesFromConfiguredPrefix() {
        contextRunner
                .withPropertyValues(
                        "ai.codegen.max-concurrent-requests=12",
                        "ai.codegen.permit-lease-minutes=45"
                )
                .run(context -> {
                    AiCodegenProperties properties = context.getBean(AiCodegenProperties.class);

                    assertThat(properties.getMaxConcurrentRequests()).isEqualTo(12);
                    assertThat(properties.getPermitLeaseMinutes()).isEqualTo(45);
                });
    }

    @Test
    void bindsIdempotencyPropertiesFromConfiguredPrefix() {
        contextRunner
                .withPropertyValues(
                        "idempotency.enabled=false",
                        "idempotency.processing-ttl-minutes=11",
                        "idempotency.ai-processing-ttl-minutes=31",
                        "idempotency.success-ttl-hours=25",
                        "idempotency.failure-ttl-minutes=6"
                )
                .run(context -> {
                    IdempotencyProperties properties = context.getBean(IdempotencyProperties.class);

                    assertThat(properties.isEnabled()).isFalse();
                    assertThat(properties.processingTtl()).isEqualTo(Duration.ofMinutes(11));
                    assertThat(properties.aiProcessingTtl()).isEqualTo(Duration.ofMinutes(31));
                    assertThat(properties.successTtl()).isEqualTo(Duration.ofHours(25));
                    assertThat(properties.failureTtl()).isEqualTo(Duration.ofMinutes(6));
                });
    }

    @Test
    void aiCodegenPropertiesExposePermitDefaults() {
        AiCodegenProperties properties = new AiCodegenProperties();

        assertThat(properties.getMaxConcurrentRequests()).isEqualTo(8);
        assertThat(properties.getPermitLeaseMinutes()).isEqualTo(30);
    }

    @Test
    void idempotencyPropertiesExposeTtls() {
        IdempotencyProperties properties = new IdempotencyProperties();

        assertThat(properties.isEnabled()).isTrue();
        assertThat(properties.processingTtl()).isEqualTo(Duration.ofMinutes(10));
        assertThat(properties.aiProcessingTtl()).isEqualTo(Duration.ofMinutes(30));
        assertThat(properties.successTtl()).isEqualTo(Duration.ofHours(24));
        assertThat(properties.failureTtl()).isEqualTo(Duration.ofMinutes(5));
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties({
            PythonAiProperties.class,
            AiCodegenProperties.class,
            IdempotencyProperties.class
    })
    static class PropertiesBindingConfig {
    }
}
