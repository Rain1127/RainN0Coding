package com.rain.rainn0coding.core.python;

import com.rain.rainn0coding.config.PythonAiProperties;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.RETURNS_SELF;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PythonAiClientTest {

    @Test
    void streamCodeGenSendsMetadataHeadersAndBodyFromProperties() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/generate-code")).thenReturn(bodySpec);
        when(bodySpec.header("X-Request-Id", "request-123")).thenReturn(bodySpec);
        when(bodySpec.header("X-Internal-Token", "secret-token")).thenReturn(bodySpec);
        when(bodySpec.header("X-Idempotency-Key", "idem-456")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.just("data: ok"));

        PythonAiProperties properties = new PythonAiProperties();
        properties.setBaseUrl("http://python-agent:8000");
        properties.setInternalToken("secret-token");
        PythonAiClient client = new PythonAiClient(builder, properties);

        List<String> result = client.streamCodeGen(
                        "1", "2", "prompt", "VUE_PROJECT", "user", "trace-123", "request-123", "idem-456")
                .collectList()
                .block();

        assertThat(result).containsExactly("data: ok");
        verify(builder).baseUrl("http://python-agent:8000");
        verify(builder).build();
        verify(bodySpec).header("X-Request-Id", "request-123");
        verify(bodySpec).header("X-Internal-Token", "secret-token");
        verify(bodySpec).header("X-Idempotency-Key", "idem-456");

        @SuppressWarnings("unchecked")
        var bodyCaptor = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(bodySpec).bodyValue(bodyCaptor.capture());
        assertThat(bodyCaptor.getValue())
                .containsEntry("traceId", "trace-123")
                .containsEntry("requestId", "request-123");
    }

    @Test
    void constructorConfiguresClientConnectorForConnectTimeout() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        when(builder.build()).thenReturn(webClient);

        PythonAiProperties properties = new PythonAiProperties();
        properties.setBaseUrl("http://python-agent:8000");
        properties.setConnectTimeoutMs(1234);

        new PythonAiClient(builder, properties);

        verify(builder).baseUrl("http://python-agent:8000");
        verify(builder).clientConnector(any(ClientHttpConnector.class));
        verify(builder).build();
    }

    @Test
    void routeCodeGenTypeUsesConfiguredRouteTimeout() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/route-codegen-type")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.never());

        PythonAiProperties properties = new PythonAiProperties();
        properties.setRouteTimeoutSeconds(0);
        PythonAiClient client = new PythonAiClient(builder, properties);

        assertThatThrownBy(() -> client.routeCodeGenType("build a todo app"))
                .isInstanceOf(RuntimeException.class);
    }

    @Test
    void routeCodeGenTypeSendsInternalTokenWhenConfigured() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/route-codegen-type")).thenReturn(bodySpec);
        when(bodySpec.header("X-Internal-Token", "secret-token")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(Map.of("codeGenType", "html")));

        PythonAiProperties properties = new PythonAiProperties();
        properties.setInternalToken("secret-token");
        PythonAiClient client = new PythonAiClient(builder, properties);

        String codeGenType = client.routeCodeGenType("build a landing page");

        assertThat(codeGenType).isEqualTo("html");
        verify(bodySpec).header("X-Internal-Token", "secret-token");
    }

    @Test
    void streamCodeGenMapsPythonOverloadToBusinessException() {
        assertStreamCodeGenMapsStatus(429, ErrorCode.AI_GENERATION_OVERLOADED);
    }

    @Test
    void streamCodeGenMapsPythonUnauthorizedToBusinessException() {
        assertStreamCodeGenMapsStatus(401, ErrorCode.PYTHON_SERVICE_UNAUTHORIZED);
    }

    @Test
    void streamCodeGenMapsPythonGatewayTimeoutToBusinessException() {
        assertStreamCodeGenMapsStatus(504, ErrorCode.PYTHON_SERVICE_TIMEOUT);
    }

    @Test
    void streamCodeGenMapsPythonServerErrorToBusinessException() {
        assertStreamCodeGenMapsStatus(500, ErrorCode.PYTHON_SERVICE_UNAVAILABLE);
    }

    @Test
    void streamCodeGenMapsPythonInternalAuthMisconfigurationToUnavailable() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/generate-code")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.error(
                WebClientResponseException.create(
                        503,
                        "Service Unavailable",
                        null,
                        "{\"detail\":\"internal authentication is misconfigured\"}".getBytes(),
                        null)
        ));

        PythonAiClient client = new PythonAiClient(builder, new PythonAiProperties());

        assertThatThrownBy(() -> client.streamCodeGen(
                        "1", "2", "prompt", "html", "user", "trace", "req", "idem")
                .collectList()
                .block())
                .isInstanceOf(BusinessException.class)
                .extracting("code")
                .isEqualTo(ErrorCode.PYTHON_SERVICE_UNAVAILABLE.getCode());
    }

    @Test
    void streamCodeGenMapsLocalResponseTimeoutToBusinessException() {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/generate-code")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.never());

        PythonAiProperties properties = new PythonAiProperties();
        properties.setResponseTimeoutSeconds(0);
        PythonAiClient client = new PythonAiClient(builder, properties);

        assertThatThrownBy(() -> client.streamCodeGen(
                        "1", "2", "prompt", "html", "user", "trace", "req", "idem")
                .collectList()
                .block())
                .isInstanceOf(BusinessException.class)
                .extracting("code")
                .isEqualTo(ErrorCode.PYTHON_SERVICE_TIMEOUT.getCode());
    }

    private void assertStreamCodeGenMapsStatus(int statusCode, ErrorCode expectedErrorCode) {
        WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
        WebClient webClient = mock(WebClient.class);
        WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
        WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
        WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
        WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

        when(builder.build()).thenReturn(webClient);
        when(webClient.post()).thenReturn(postSpec);
        when(postSpec.uri("/api/generate-code")).thenReturn(bodySpec);
        doReturn(headersSpec).when(bodySpec).bodyValue(any());
        when(headersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.error(
                WebClientResponseException.create(statusCode, "Python Error", null, null, null)
        ));

        PythonAiClient client = new PythonAiClient(builder, new PythonAiProperties());

        assertThatThrownBy(() -> client.streamCodeGen(
                        "1", "2", "prompt", "html", "user", "trace", "req", "idem")
                .collectList()
                .block())
                .isInstanceOf(BusinessException.class)
                .extracting("code")
                .isEqualTo(expectedErrorCode.getCode());
    }
}
