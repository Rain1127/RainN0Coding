package com.rain.rainn0coding.core.python;

import com.rain.rainn0coding.config.PythonAiProperties;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import io.netty.channel.ChannelOption;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.netty.http.client.HttpClient;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;

/**
 * Java side proxy for the Python agent service.
 */
@Component
public class PythonAiClient {

    private final WebClient webClient;
    private final PythonAiProperties properties;

    public PythonAiClient(WebClient.Builder builder, PythonAiProperties properties) {
        this.properties = properties;
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, (int) properties.getConnectTimeout().toMillis());
        this.webClient = builder
                .baseUrl(properties.getBaseUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(config -> config.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
                .build();
    }

    public Flux<String> streamCodeGen(String userId, String appId,
                                      String prompt, String codeGenType,
                                      String userRole, String traceId) {
        return streamCodeGen(userId, appId, prompt, codeGenType, userRole, traceId, null, null);
    }

    public Flux<String> streamCodeGen(String userId, String appId,
                                      String prompt, String codeGenType,
                                      String userRole, String traceId,
                                      String requestId, String idempotencyKey) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("userId", userId);
        body.put("appId", appId);
        body.put("prompt", prompt);
        body.put("codeGenType", codeGenType);
        body.put("userRole", userRole != null ? userRole : "user");
        body.put("traceId", traceId != null ? traceId : "");
        body.put("requestId", requestId != null ? requestId : "");
        body.put("history", List.of());

        WebClient.RequestBodySpec request = webClient.post()
                .uri("/api/generate-code");
        if (StringUtils.hasText(requestId)) {
            request.header("X-Request-Id", requestId);
        }
        if (StringUtils.hasText(properties.getInternalToken())) {
            request.header("X-Internal-Token", properties.getInternalToken());
        }
        if (StringUtils.hasText(idempotencyKey)) {
            request.header("X-Idempotency-Key", idempotencyKey);
        }

        return request
                .bodyValue(body)
                .retrieve()
                .bodyToFlux(String.class)
                .timeout(properties.getResponseTimeout())
                .onErrorMap(WebClientResponseException.class, this::mapPythonResponseException)
                .onErrorMap(TimeoutException.class,
                        exception -> new BusinessException(ErrorCode.PYTHON_SERVICE_TIMEOUT));
    }

    public String routeCodeGenType(String prompt) {
        Map<String, Object> body = Map.of("prompt", prompt);
        WebClient.RequestBodySpec request = webClient.post()
                .uri("/api/route-codegen-type");
        if (StringUtils.hasText(properties.getInternalToken())) {
            request.header("X-Internal-Token", properties.getInternalToken());
        }

        Map<?, ?> response = request
                .bodyValue(body)
                .retrieve()
                .bodyToMono(Map.class)
                .block(properties.getRouteTimeout());
        if (response == null) {
            return null;
        }
        Object codeGenType = response.get("codeGenType");
        return codeGenType != null ? codeGenType.toString() : null;
    }

    private BusinessException mapPythonResponseException(WebClientResponseException exception) {
        HttpStatus status = HttpStatus.resolve(exception.getStatusCode().value());
        if (status == HttpStatus.SERVICE_UNAVAILABLE && isInternalAuthMisconfigured(exception)) {
            return new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE);
        }
        if (status == HttpStatus.TOO_MANY_REQUESTS || status == HttpStatus.SERVICE_UNAVAILABLE) {
            return new BusinessException(ErrorCode.AI_GENERATION_OVERLOADED);
        }
        if (status == HttpStatus.UNAUTHORIZED || status == HttpStatus.FORBIDDEN) {
            return new BusinessException(ErrorCode.PYTHON_SERVICE_UNAUTHORIZED);
        }
        if (status == HttpStatus.GATEWAY_TIMEOUT) {
            return new BusinessException(ErrorCode.PYTHON_SERVICE_TIMEOUT);
        }
        if (exception.getStatusCode().is5xxServerError()) {
            return new BusinessException(ErrorCode.PYTHON_SERVICE_UNAVAILABLE);
        }
        return new BusinessException(ErrorCode.SYSTEM_ERROR, exception.getMessage());
    }

    private boolean isInternalAuthMisconfigured(WebClientResponseException exception) {
        String body = exception.getResponseBodyAsString();
        return body != null && body.contains("internal authentication is misconfigured");
    }
}
