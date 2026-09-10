package com.rain.rainn0coding.core.python;

import com.rain.rainn0coding.config.PythonAiProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PythonGenerationControlTest {
    private final WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
    private final WebClient web = mock(WebClient.class);
    private final WebClient.RequestBodyUriSpec post = mock(WebClient.RequestBodyUriSpec.class);
    private final WebClient.RequestBodySpec body = mock(WebClient.RequestBodySpec.class, RETURNS_SELF);
    private final WebClient.RequestHeadersSpec<?> headers = mock(WebClient.RequestHeadersSpec.class);
    private final WebClient.ResponseSpec response = mock(WebClient.ResponseSpec.class);
    private PythonAiClient client;

    @BeforeEach
    void setUp() {
        when(builder.build()).thenReturn(web);
        when(web.post()).thenReturn(post);
        when(post.uri(anyString())).thenReturn(body);
        doReturn(headers).when(body).bodyValue(any());
        when(headers.retrieve()).thenReturn(response);
        PythonAiProperties properties = new PythonAiProperties();
        properties.setInternalToken("internal-test-token");
        client = new PythonAiClient(builder, properties);
    }

    @Test
    void pauseForwardsTrustedIdentifiersWithInternalToken() {
        Map<String, Object> result = Map.of("run_id", "run", "status", "pausing");
        when(response.bodyToMono(any(ParameterizedTypeReference.class))).thenReturn(Mono.just(result));
        assertThat(client.pauseGeneration("7", "12", "run")).isEqualTo(result);
        verify(post).uri("/api/generation/pause");
        verify(body).header("X-Internal-Token", "internal-test-token");
        verify(body).bodyValue(Map.of("userId", "7", "appId", "12", "runId", "run"));
    }

    @Test
    void statusUsesAuthenticatedControlEndpoint() {
        Map<String, Object> result = Map.of("run_id", "run", "status", "paused");
        when(response.bodyToMono(any(ParameterizedTypeReference.class))).thenReturn(Mono.just(result));
        assertThat(client.generationStatus("7", "12", "run")).isEqualTo(result);
        verify(post).uri("/api/generation/status");
        verify(body).header("X-Internal-Token", "internal-test-token");
        verify(body).bodyValue(Map.of("userId", "7", "appId", "12", "runId", "run"));
    }

    @Test
    void resumeSendsTrueAndStableRunIdWithEmptyPrompt() {
        when(response.bodyToFlux(String.class)).thenReturn(Flux.just("done"));
        client.streamCodeGen("7", "12", "", "html", "user", "trace", "run", null, true)
                .collectList().block();
        var captured = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(body).bodyValue(captured.capture());
        assertThat(captured.getValue()).containsEntry("resume", true).containsEntry("requestId", "run")
                .containsEntry("prompt", "").containsEntry("userId", "7").containsEntry("appId", "12");
        verify(body).header("X-Request-Id", "run");
        verify(body).header("X-Internal-Token", "internal-test-token");
        verify(body, never()).header(eq("X-Idempotency-Key"), anyString());
    }
}
