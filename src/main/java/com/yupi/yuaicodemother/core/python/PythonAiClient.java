package com.yupi.yuaicodemother.core.python;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Python AI Agent 代理客户端。
 *
 * Java 不再直接调用 DeepSeek/LangChain4j，
 * 而是通过此客户端将请求转发到 Python FastAPI（7-Agent + RAG），
 * 并透传 SSE 事件流给前端。
 */
@Component
public class PythonAiClient {

    private final WebClient webClient;

    public PythonAiClient(@Value("${python.ai.base-url}") String baseUrl) {
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .codecs(config -> config.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
                .build();
    }

    /**
     * 流式代码生成 —— 调用 Python POST /api/generate-code (SSE)。
     *
     * @param userId      用户 ID
     * @param appId       应用 ID
     * @param prompt      用户需求文本
     * @param codeGenType 代码生成类型 (VUE_PROJECT / HTML / MULTI_FILE)
     * @return SSE 事件行 Flux（每行即一个 JSON 事件）
     */
    public Flux<String> streamCodeGen(String userId, String appId,
                                       String prompt, String codeGenType,
                                       String userRole, String traceId) {
        Map<String, Object> body = Map.of(
                "userId", userId,
                "appId", appId,
                "prompt", prompt,
                "codeGenType", codeGenType,
                "userRole", userRole != null ? userRole : "user",
                "traceId", traceId != null ? traceId : "",
                "history", List.of()
        );

        return webClient.post()
                .uri("/api/generate-code")
                .bodyValue(body)
                .retrieve()
                .bodyToFlux(String.class);
    }

    /**
     * Python 服务健康检查。
     */
    public boolean healthCheck() {
        try {
            String result = webClient.get()
                    .uri("/api/health")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5));
            return result != null && result.contains("\"status\":\"ok\"");
        } catch (Exception e) {
            return false;
        }
    }
}
