# Production Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first production-hardening baseline for idempotency, high-concurrency admission, Java-to-Python authentication, Python client reliability, and deterministic harness tests.

**Architecture:** Java remains the public gateway and owns idempotency, request fingerprinting, global AI admission, and Python client reliability. Python remains the Agent runtime and adds internal-token authentication plus a local concurrency semaphore so direct or multi-gateway traffic cannot overload the Agent process.

**Tech Stack:** Spring Boot 3.5.9, Java 21/23, Redisson, WebFlux WebClient, JUnit 5, Mockito, Reactor Test if already present; FastAPI, pytest, httpx/TestClient, asyncio.

---

## File Structure

- Create `src/main/java/com/yupi/yuaicodemother/config/PythonAiProperties.java`: typed Java properties for Python base URL, token, and timeout budgets.
- Create `src/main/java/com/yupi/yuaicodemother/config/AiCodegenProperties.java`: typed Java properties for generation concurrency permits.
- Create `src/main/java/com/yupi/yuaicodemother/config/IdempotencyProperties.java`: typed Java properties for idempotency TTLs and enablement.
- Modify `src/main/resources/application.yml`: add the new property defaults.
- Modify `src/main/java/com/yupi/yuaicodemother/exception/ErrorCode.java`: add specific production-baseline error codes.
- Create `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyStatus.java`: enum for `PROCESSING`, `SUCCESS`, `FAILED`.
- Create `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyRecord.java`: serializable Redis record.
- Create `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyDecision.java`: result object returned by idempotency start checks.
- Create `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyService.java`: Redis-backed idempotency state machine.
- Create `src/main/java/com/yupi/yuaicodemother/concurrency/AiGenerationPermitService.java`: Redisson-backed global AI permit service.
- Modify `src/main/java/com/yupi/yuaicodemother/core/python/PythonAiClient.java`: add headers, request IDs, token, timeouts, and safer error mapping.
- Modify `src/main/java/com/yupi/yuaicodemother/service/AppService.java`: add idempotency/request-id aware overload for chat generation.
- Modify `src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java`: acquire global permits and mark idempotency state around AI generation.
- Modify `src/main/java/com/yupi/yuaicodemother/controller/AppController.java`: read `Idempotency-Key`, call idempotent wrappers for add/deploy, and pass idempotency metadata to chat.
- Modify `python-agent/config.py`: add `INTERNAL_API_TOKEN`, `AGENT_MAX_CONCURRENT_REQUESTS`, and `AGENT_OVERLOAD_STATUS_CODE`.
- Modify `python-agent/server/main.py`: add internal-token middleware, local semaphore, request id fields, and structured overload behavior.
- Create or extend Java tests under `src/test/java/com/yupi/yuaicodemother/...`.
- Create Python tests under `python-agent/tests/test_internal_auth_and_concurrency.py`.
- Create `docs/production-hardening-harness.md`: local verification guide.

---

### Task 1: Configuration and Error Codes

**Files:**
- Create: `src/main/java/com/yupi/yuaicodemother/config/PythonAiProperties.java`
- Create: `src/main/java/com/yupi/yuaicodemother/config/AiCodegenProperties.java`
- Create: `src/main/java/com/yupi/yuaicodemother/config/IdempotencyProperties.java`
- Modify: `src/main/resources/application.yml`
- Modify: `src/main/java/com/yupi/yuaicodemother/exception/ErrorCode.java`
- Test: `src/test/java/com/yupi/yuaicodemother/config/ProductionBaselinePropertiesTest.java`

- [ ] **Step 1: Write the failing properties test**

```java
package com.yupi.yuaicodemother.config;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionBaselinePropertiesTest {

    @Test
    void pythonAiPropertiesExposeTimeoutsAndInternalToken() {
        PythonAiProperties properties = new PythonAiProperties();
        properties.setBaseUrl("http://python:8000");
        properties.setInternalToken("secret");
        properties.setConnectTimeoutMs(2500);
        properties.setResponseTimeoutSeconds(120);
        properties.setRouteTimeoutSeconds(5);

        assertThat(properties.getBaseUrl()).isEqualTo("http://python:8000");
        assertThat(properties.getInternalToken()).isEqualTo("secret");
        assertThat(properties.getConnectTimeout()).isEqualTo(Duration.ofMillis(2500));
        assertThat(properties.getResponseTimeout()).isEqualTo(Duration.ofSeconds(120));
        assertThat(properties.getRouteTimeout()).isEqualTo(Duration.ofSeconds(5));
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
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=ProductionBaselinePropertiesTest
```

Expected: compilation fails because the three properties classes do not exist.

- [ ] **Step 3: Add the properties classes**

Create `PythonAiProperties.java`:

```java
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
```

Create `AiCodegenProperties.java`:

```java
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
```

Create `IdempotencyProperties.java`:

```java
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
```

- [ ] **Step 4: Add application defaults**

In `src/main/resources/application.yml`, extend the existing `python.ai` block and add `ai.codegen` plus `idempotency`:

```yaml
python:
  ai:
    base-url: ${PYTHON_AI_BASE_URL:http://localhost:8000}
    internal-token: ${PYTHON_AI_INTERNAL_TOKEN:}
    connect-timeout-ms: ${PYTHON_AI_CONNECT_TIMEOUT_MS:3000}
    response-timeout-seconds: ${PYTHON_AI_RESPONSE_TIMEOUT_SECONDS:1800}
    route-timeout-seconds: ${PYTHON_AI_ROUTE_TIMEOUT_SECONDS:30}

ai:
  codegen:
    max-concurrent-requests: ${AI_CODEGEN_MAX_CONCURRENT_REQUESTS:8}
    permit-lease-minutes: ${AI_CODEGEN_PERMIT_LEASE_MINUTES:30}

idempotency:
  enabled: ${IDEMPOTENCY_ENABLED:true}
  processing-ttl-minutes: ${IDEMPOTENCY_PROCESSING_TTL_MINUTES:10}
  ai-processing-ttl-minutes: ${IDEMPOTENCY_AI_PROCESSING_TTL_MINUTES:30}
  success-ttl-hours: ${IDEMPOTENCY_SUCCESS_TTL_HOURS:24}
  failure-ttl-minutes: ${IDEMPOTENCY_FAILURE_TTL_MINUTES:5}
```

- [ ] **Step 5: Add error codes**

Update `ErrorCode.java` with these enum constants before `SYSTEM_ERROR`:

```java
REQUEST_IN_PROGRESS(42902, "请求正在处理中"),
REQUEST_REPLAY_CONFLICT(40900, "幂等键已被不同请求使用"),
AI_GENERATION_OVERLOADED(42903, "AI 生成服务繁忙"),
PYTHON_SERVICE_UNAUTHORIZED(50201, "Python Agent 鉴权失败"),
PYTHON_SERVICE_TIMEOUT(50400, "Python Agent 响应超时"),
PYTHON_SERVICE_UNAVAILABLE(50300, "Python Agent 暂不可用"),
```

- [ ] **Step 6: Run the properties test**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=ProductionBaselinePropertiesTest
```

Expected: test passes.

---

### Task 2: Redis-Backed Idempotency Service

**Files:**
- Create: `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyStatus.java`
- Create: `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyRecord.java`
- Create: `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyDecision.java`
- Create: `src/main/java/com/yupi/yuaicodemother/idempotency/IdempotencyService.java`
- Test: `src/test/java/com/yupi/yuaicodemother/idempotency/IdempotencyServiceTest.java`

- [ ] **Step 1: Write the failing idempotency tests**

```java
package com.yupi.yuaicodemother.idempotency;

import com.yupi.yuaicodemother.config.IdempotencyProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RBucket;
import org.redisson.api.RedissonClient;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IdempotencyServiceTest {

    private RedissonClient redissonClient;
    private RBucket<IdempotencyRecord> bucket;
    private IdempotencyService idempotencyService;

    @BeforeEach
    void setUp() {
        redissonClient = mock(RedissonClient.class);
        bucket = mock(RBucket.class);
        when(redissonClient.<IdempotencyRecord>getBucket(any())).thenReturn(bucket);
        idempotencyService = new IdempotencyService(redissonClient, new IdempotencyProperties());
    }

    @Test
    void blankKeyBypassesIdempotency() {
        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.BYPASS);
    }

    @Test
    void missingRecordStartsProcessing() {
        when(bucket.get()).thenReturn(null);

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.STARTED);
        verify(bucket).set(any(IdempotencyRecord.class), eq(Duration.ofMinutes(1)));
    }

    @Test
    void fingerprintMismatchIsConflict() {
        when(bucket.get()).thenReturn(IdempotencyRecord.processing("other-fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.FINGERPRINT_MISMATCH);
    }

    @Test
    void successRecordIsReplayable() {
        IdempotencyRecord record = IdempotencyRecord.success("fp", "{\"data\":123}", 200);
        when(bucket.get()).thenReturn(record);

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.REPLAY_SUCCESS);
        assertThat(decision.record()).isSameAs(record);
    }

    @Test
    void processingRecordRejectsDuplicate() {
        when(bucket.get()).thenReturn(IdempotencyRecord.processing("fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.IN_PROGRESS);
    }
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=IdempotencyServiceTest
```

Expected: compilation fails because idempotency classes do not exist.

- [ ] **Step 3: Add idempotency model classes**

Create `IdempotencyStatus.java`:

```java
package com.yupi.yuaicodemother.idempotency;

public enum IdempotencyStatus {
    PROCESSING,
    SUCCESS,
    FAILED
}
```

Create `IdempotencyRecord.java`:

```java
package com.yupi.yuaicodemother.idempotency;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import java.time.Instant;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class IdempotencyRecord implements Serializable {

    private IdempotencyStatus status;
    private String fingerprint;
    private String resultJson;
    private Integer httpStatus;
    private Integer errorCode;
    private String errorMessage;
    private Instant createdAt;
    private Instant updatedAt;

    public static IdempotencyRecord processing(String fingerprint) {
        Instant now = Instant.now();
        return new IdempotencyRecord(IdempotencyStatus.PROCESSING, fingerprint, null, null, null, null, now, now);
    }

    public static IdempotencyRecord success(String fingerprint, String resultJson, int httpStatus) {
        Instant now = Instant.now();
        return new IdempotencyRecord(IdempotencyStatus.SUCCESS, fingerprint, resultJson, httpStatus, null, null, now, now);
    }

    public static IdempotencyRecord failed(String fingerprint, int errorCode, String errorMessage) {
        Instant now = Instant.now();
        return new IdempotencyRecord(IdempotencyStatus.FAILED, fingerprint, null, null, errorCode, errorMessage, now, now);
    }
}
```

Create `IdempotencyDecision.java`:

```java
package com.yupi.yuaicodemother.idempotency;

public record IdempotencyDecision(Type type, String redisKey, IdempotencyRecord record) {

    public enum Type {
        BYPASS,
        STARTED,
        IN_PROGRESS,
        REPLAY_SUCCESS,
        REPLAY_FAILED,
        FINGERPRINT_MISMATCH
    }

    public static IdempotencyDecision bypass() {
        return new IdempotencyDecision(Type.BYPASS, null, null);
    }

    public static IdempotencyDecision of(Type type, String redisKey, IdempotencyRecord record) {
        return new IdempotencyDecision(type, redisKey, record);
    }
}
```

- [ ] **Step 4: Add `IdempotencyService`**

```java
package com.yupi.yuaicodemother.idempotency;

import cn.hutool.core.util.StrUtil;
import com.yupi.yuaicodemother.config.IdempotencyProperties;
import jakarta.annotation.Resource;
import org.redisson.api.RBucket;
import org.redisson.api.RedissonClient;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;

@Service
public class IdempotencyService {

    private final RedissonClient redissonClient;
    private final IdempotencyProperties properties;

    public IdempotencyService(RedissonClient redissonClient, IdempotencyProperties properties) {
        this.redissonClient = redissonClient;
        this.properties = properties;
    }

    public IdempotencyDecision start(String operation, Long userId, String rawKey, String fingerprint, Duration processingTtl) {
        if (!properties.isEnabled() || StrUtil.isBlank(rawKey)) {
            return IdempotencyDecision.bypass();
        }
        String redisKey = redisKey(operation, userId, rawKey);
        RBucket<IdempotencyRecord> bucket = redissonClient.getBucket(redisKey);
        IdempotencyRecord existing = bucket.get();
        if (existing == null) {
            bucket.set(IdempotencyRecord.processing(fingerprint), processingTtl);
            return IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, redisKey, null);
        }
        if (!fingerprint.equals(existing.getFingerprint())) {
            return IdempotencyDecision.of(IdempotencyDecision.Type.FINGERPRINT_MISMATCH, redisKey, existing);
        }
        if (existing.getStatus() == IdempotencyStatus.SUCCESS) {
            return IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_SUCCESS, redisKey, existing);
        }
        if (existing.getStatus() == IdempotencyStatus.FAILED) {
            return IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_FAILED, redisKey, existing);
        }
        return IdempotencyDecision.of(IdempotencyDecision.Type.IN_PROGRESS, redisKey, existing);
    }

    public void markSuccess(String redisKey, String fingerprint, String resultJson, int httpStatus) {
        if (StrUtil.isBlank(redisKey)) {
            return;
        }
        redissonClient.<IdempotencyRecord>getBucket(redisKey)
                .set(IdempotencyRecord.success(fingerprint, resultJson, httpStatus), properties.successTtl());
    }

    public void markFailed(String redisKey, String fingerprint, int errorCode, String errorMessage) {
        if (StrUtil.isBlank(redisKey)) {
            return;
        }
        redissonClient.<IdempotencyRecord>getBucket(redisKey)
                .set(IdempotencyRecord.failed(fingerprint, errorCode, errorMessage), properties.failureTtl());
    }

    public String fingerprint(String operation, Object... parts) {
        StringBuilder builder = new StringBuilder(operation);
        for (Object part : parts) {
            builder.append('\n').append(part == null ? "" : part);
        }
        return sha256(builder.toString());
    }

    private String redisKey(String operation, Long userId, String rawKey) {
        return "idempotency:" + operation + ":" + userId + ":" + sha256(rawKey);
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
```

- [ ] **Step 5: Run the idempotency tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=IdempotencyServiceTest
```

Expected: tests pass.

---

### Task 3: Global AI Generation Permit Service

**Files:**
- Create: `src/main/java/com/yupi/yuaicodemother/concurrency/AiGenerationPermitService.java`
- Test: `src/test/java/com/yupi/yuaicodemother/concurrency/AiGenerationPermitServiceTest.java`

- [ ] **Step 1: Write the failing permit tests**

```java
package com.yupi.yuaicodemother.concurrency;

import com.yupi.yuaicodemother.config.AiCodegenProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RPermitExpirableSemaphore;
import org.redisson.api.RedissonClient;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiGenerationPermitServiceTest {

    private RPermitExpirableSemaphore semaphore;
    private AiGenerationPermitService service;

    @BeforeEach
    void setUp() {
        RedissonClient redissonClient = mock(RedissonClient.class);
        semaphore = mock(RPermitExpirableSemaphore.class);
        when(redissonClient.getPermitExpirableSemaphore("ai:codegen:permits")).thenReturn(semaphore);

        AiCodegenProperties properties = new AiCodegenProperties();
        properties.setMaxConcurrentRequests(2);
        properties.setPermitLeaseMinutes(30);
        service = new AiGenerationPermitService(redissonClient, properties);
    }

    @Test
    void acquireReturnsHandleWhenPermitAvailable() throws Exception {
        when(semaphore.trySetPermits(2)).thenReturn(true);
        when(semaphore.tryAcquire(0, 30, TimeUnit.MINUTES)).thenReturn("permit-1");

        AiGenerationPermitService.PermitHandle handle = service.tryAcquire();

        assertThat(handle.acquired()).isTrue();
        assertThat(handle.permitId()).isEqualTo("permit-1");
    }

    @Test
    void acquireReturnsEmptyHandleWhenOverloaded() throws Exception {
        when(semaphore.trySetPermits(2)).thenReturn(false);
        when(semaphore.tryAcquire(0, 30, TimeUnit.MINUTES)).thenReturn(null);

        AiGenerationPermitService.PermitHandle handle = service.tryAcquire();

        assertThat(handle.acquired()).isFalse();
    }

    @Test
    void releaseUsesPermitId() throws Exception {
        AiGenerationPermitService.PermitHandle handle = new AiGenerationPermitService.PermitHandle(true, "permit-1");

        service.release(handle);

        verify(semaphore).release("permit-1");
    }
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=AiGenerationPermitServiceTest
```

Expected: compilation fails because `AiGenerationPermitService` does not exist.

- [ ] **Step 3: Add the permit service**

```java
package com.yupi.yuaicodemother.concurrency;

import com.yupi.yuaicodemother.config.AiCodegenProperties;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RPermitExpirableSemaphore;
import org.redisson.api.RedissonClient;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
@Slf4j
public class AiGenerationPermitService {

    private static final String PERMIT_KEY = "ai:codegen:permits";

    private final RPermitExpirableSemaphore semaphore;
    private final AiCodegenProperties properties;

    public AiGenerationPermitService(RedissonClient redissonClient, AiCodegenProperties properties) {
        this.semaphore = redissonClient.getPermitExpirableSemaphore(PERMIT_KEY);
        this.properties = properties;
    }

    public PermitHandle tryAcquire() {
        try {
            semaphore.trySetPermits(properties.getMaxConcurrentRequests());
            String permitId = semaphore.tryAcquire(0, properties.getPermitLeaseMinutes(), TimeUnit.MINUTES);
            return new PermitHandle(permitId != null, permitId);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return PermitHandle.notAcquired();
        }
    }

    public void release(PermitHandle handle) {
        if (handle == null || !handle.acquired() || handle.permitId() == null) {
            return;
        }
        try {
            semaphore.release(handle.permitId());
        } catch (Exception e) {
            log.warn("Failed to release AI generation permit {}", handle.permitId(), e);
        }
    }

    public record PermitHandle(boolean acquired, String permitId) {
        public static PermitHandle notAcquired() {
            return new PermitHandle(false, null);
        }
    }
}
```

- [ ] **Step 4: Run the permit tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=AiGenerationPermitServiceTest
```

Expected: tests pass.

---

### Task 4: Harden `PythonAiClient`

**Files:**
- Modify: `src/main/java/com/yupi/yuaicodemother/core/python/PythonAiClient.java`
- Modify: `src/test/java/com/yupi/yuaicodemother/core/python/PythonAiClientTest.java`

- [ ] **Step 1: Replace the existing client test with header and timeout coverage**

Add or update tests in `PythonAiClientTest.java`:

```java
@Test
void streamCodeGenSendsInternalHeadersAndIdempotencyMetadata() {
    WebClient.Builder builder = mock(WebClient.Builder.class, RETURNS_SELF);
    WebClient webClient = mock(WebClient.class);
    WebClient.RequestBodyUriSpec postSpec = mock(WebClient.RequestBodyUriSpec.class);
    WebClient.RequestBodySpec bodySpec = mock(WebClient.RequestBodySpec.class);
    WebClient.RequestBodySpec headerSpec = mock(WebClient.RequestBodySpec.class);
    WebClient.RequestHeadersSpec headersSpec = mock(WebClient.RequestHeadersSpec.class);
    WebClient.ResponseSpec responseSpec = mock(WebClient.ResponseSpec.class);

    when(builder.build()).thenReturn(webClient);
    when(webClient.post()).thenReturn(postSpec);
    when(postSpec.uri("/api/generate-code")).thenReturn(bodySpec);
    when(bodySpec.header(any(), any())).thenReturn(headerSpec);
    when(headerSpec.header(any(), any())).thenReturn(headerSpec);
    doReturn(headersSpec).when(headerSpec).bodyValue(any());
    when(headersSpec.retrieve()).thenReturn(responseSpec);
    when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.just("data: ok"));

    PythonAiProperties properties = new PythonAiProperties();
    properties.setBaseUrl("http://python-agent:8000");
    properties.setInternalToken("secret-token");
    PythonAiClient client = new PythonAiClient(builder, properties);

    List<String> result = client.streamCodeGen(
                    "1", "2", "prompt", "VUE_PROJECT", "user",
                    "trace-123", "request-123", "idem-123")
            .collectList()
            .block();

    assertThat(result).containsExactly("data: ok");
    verify(bodySpec).header("X-Internal-Token", "secret-token");
    verify(headerSpec).header("X-Request-Id", "request-123");
    verify(headerSpec).header("X-Idempotency-Key", "idem-123");
}
```

- [ ] **Step 2: Run the client test and verify it fails**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=PythonAiClientTest
```

Expected: compilation fails because the constructor and `streamCodeGen` signature do not match.

- [ ] **Step 3: Update `PythonAiClient` constructor and stream method**

Change constructor to accept `PythonAiProperties` and change `streamCodeGen` to include `requestId` and `idempotencyKey`:

```java
public PythonAiClient(WebClient.Builder builder, PythonAiProperties properties) {
    this.properties = properties;
    this.webClient = builder
            .baseUrl(properties.getBaseUrl())
            .codecs(config -> config.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
            .build();
}

public Flux<String> streamCodeGen(String userId, String appId,
                                  String prompt, String codeGenType,
                                  String userRole, String traceId,
                                  String requestId, String idempotencyKey) {
    Map<String, Object> body = Map.of(
            "userId", userId,
            "appId", appId,
            "prompt", prompt,
            "codeGenType", codeGenType,
            "userRole", userRole != null ? userRole : "user",
            "traceId", traceId != null ? traceId : "",
            "requestId", requestId != null ? requestId : "",
            "history", List.of()
    );

    WebClient.RequestBodySpec request = webClient.post()
            .uri("/api/generate-code")
            .header("X-Request-Id", requestId != null ? requestId : "");
    if (StrUtil.isNotBlank(properties.getInternalToken())) {
        request = request.header("X-Internal-Token", properties.getInternalToken());
    }
    if (StrUtil.isNotBlank(idempotencyKey)) {
        request = request.header("X-Idempotency-Key", idempotencyKey);
    }
    return request.bodyValue(body)
            .retrieve()
            .bodyToFlux(String.class)
            .timeout(properties.getResponseTimeout());
}
```

Add `private final PythonAiProperties properties;` and imports for `StrUtil` and `PythonAiProperties`.

- [ ] **Step 4: Update `routeCodeGenType` timeout**

Replace `.block(Duration.ofSeconds(30))` with:

```java
.block(properties.getRouteTimeout());
```

- [ ] **Step 5: Run the client tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=PythonAiClientTest
```

Expected: tests pass.

---

### Task 5: Wire Idempotency and Concurrency into Java App Flow

**Files:**
- Modify: `src/main/java/com/yupi/yuaicodemother/service/AppService.java`
- Modify: `src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java`
- Modify: `src/main/java/com/yupi/yuaicodemother/controller/AppController.java`
- Test: `src/test/java/com/yupi/yuaicodemother/controller/AppControllerProductionBaselineTest.java`
- Test: `src/test/java/com/yupi/yuaicodemother/service/impl/AppServiceImplProductionBaselineTest.java`

- [ ] **Step 1: Write controller tests for add idempotency replay**

```java
package com.yupi.yuaicodemother.controller;

import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.common.BaseResponse;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.idempotency.IdempotencyDecision;
import com.yupi.yuaicodemother.idempotency.IdempotencyRecord;
import com.yupi.yuaicodemother.idempotency.IdempotencyService;
import com.yupi.yuaicodemother.model.dto.app.AppAddRequest;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.service.AppService;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AppControllerProductionBaselineTest {

    @Test
    void addAppReplaysSuccessfulIdempotentResponse() {
        AppController controller = new AppController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "appService", appService);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint(any(), any())).thenReturn("fp");
        BaseResponse<Long> cached = new BaseResponse<>(0, 99L, "");
        IdempotencyRecord record = IdempotencyRecord.success("fp", JSONUtil.toJsonStr(cached), 200);
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.REPLAY_SUCCESS, "redis-key", record));

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");
        BaseResponse<Long> response = controller.addApp(body, "idem", request);

        assertThat(response.getData()).isEqualTo(99L);
    }

    @Test
    void addAppRejectsFingerprintConflict() {
        AppController controller = new AppController();
        UserService userService = mock(UserService.class);
        IdempotencyService idempotencyService = mock(IdempotencyService.class);
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(controller, "userService", userService);
        ReflectionTestUtils.setField(controller, "idempotencyService", idempotencyService);

        User user = new User();
        user.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(user);
        when(idempotencyService.fingerprint(any(), any())).thenReturn("fp");
        when(idempotencyService.start("app:add", 1L, "idem", "fp", Duration.ofMinutes(10)))
                .thenReturn(IdempotencyDecision.of(IdempotencyDecision.Type.FINGERPRINT_MISMATCH, "redis-key", null));

        AppAddRequest body = new AppAddRequest();
        body.setInitPrompt("build app");

        org.junit.jupiter.api.Assertions.assertThrows(
                com.yupi.yuaicodemother.exception.BusinessException.class,
                () -> controller.addApp(body, "idem", request)
        );
    }
}
```

- [ ] **Step 2: Run controller tests and verify they fail**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=AppControllerProductionBaselineTest
```

Expected: compilation fails because `AppController.addApp` does not accept the idempotency header and does not have `idempotencyService`.

- [ ] **Step 3: Update `AppController.addApp`**

Change the signature:

```java
public BaseResponse<Long> addApp(@RequestBody AppAddRequest appAddRequest,
                                 @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                 HttpServletRequest request)
```

Inject:

```java
@Resource
private IdempotencyService idempotencyService;

@Resource
private IdempotencyProperties idempotencyProperties;
```

Add flow after login user:

```java
String fingerprint = idempotencyService.fingerprint("app:add", appAddRequest.getInitPrompt());
IdempotencyDecision decision = idempotencyService.start(
        "app:add", loginUser.getId(), idempotencyKey, fingerprint, idempotencyProperties.processingTtl());
if (decision.type() == IdempotencyDecision.Type.REPLAY_SUCCESS) {
    return JSONUtil.toBean(decision.record().getResultJson(), BaseResponse.class);
}
if (decision.type() == IdempotencyDecision.Type.FINGERPRINT_MISMATCH) {
    throw new BusinessException(ErrorCode.REQUEST_REPLAY_CONFLICT);
}
if (decision.type() == IdempotencyDecision.Type.IN_PROGRESS) {
    throw new BusinessException(ErrorCode.REQUEST_IN_PROGRESS);
}
try {
    Long appId = appService.createApp(appAddRequest, loginUser);
    BaseResponse<Long> response = ResultUtils.success(appId);
    idempotencyService.markSuccess(decision.redisKey(), fingerprint, JSONUtil.toJsonStr(response), 200);
    return response;
} catch (BusinessException e) {
    idempotencyService.markFailed(decision.redisKey(), fingerprint, e.getCode(), e.getMessage());
    throw e;
}
```

- [ ] **Step 4: Apply the same idempotency pattern to `deployApp`**

Change signature:

```java
public BaseResponse<String> deployApp(@RequestBody AppDeployRequest appDeployRequest,
                                      @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                      HttpServletRequest request)
```

Use operation `app:deploy` and fingerprint parts `appId`.

- [ ] **Step 5: Add AppService overload for chat metadata**

In `AppService.java`, add:

```java
Flux<String> chatToGenCode(Long appId, String message, User loginUser, String requestId, String idempotencyKey);
```

Keep the existing method as a compatibility default in `AppServiceImpl`:

```java
@Override
public Flux<String> chatToGenCode(Long appId, String message, User loginUser) {
    return chatToGenCode(appId, message, loginUser, null, null);
}
```

- [ ] **Step 6: Wire global permits into `AppServiceImpl.chatToGenCode`**

Inject:

```java
@Resource
private AiGenerationPermitService aiGenerationPermitService;
```

Before calling `aiCodeGeneratorFacade.generateAndSaveCodeStream`, acquire:

```java
AiGenerationPermitService.PermitHandle permit = aiGenerationPermitService.tryAcquire();
if (!permit.acquired()) {
    return Flux.just(
            "{\"type\":\"error\",\"status\":\"overloaded\",\"message\":\"AI generation capacity is full. Please retry later.\"}",
            "{\"type\":\"done\",\"status\":\"overloaded\"}"
    );
}
```

Release in `doFinally`:

```java
aiGenerationPermitService.release(permit);
```

- [ ] **Step 7: Pass request metadata through the facade/client path**

Update `AiCodeGeneratorFacade.generateAndSaveCodeStream(...)` only as narrowly as needed so it can pass `requestId` and `idempotencyKey` to `PythonAiClient.streamCodeGen`.

If changing the facade signature causes broad test churn, add an overload:

```java
public Flux<String> generateAndSaveCodeStream(String userMessage, CodeGenTypeEnum codeGenType,
                                              Long appId, Long userId, String userRole,
                                              String requestId, String idempotencyKey)
```

The existing method should delegate with `null` metadata.

- [ ] **Step 8: Update chat controller idempotency behavior**

In `AppController.chatToGenCode`, read:

```java
@RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey
```

Generate:

```java
String requestId = StrUtil.isNotBlank(idempotencyKey) ? idempotencyKey : java.util.UUID.randomUUID().toString();
```

Use operation `app:chat:gen-code` and fingerprint parts `appId`, `message`. If `IN_PROGRESS`, return:

```java
return Flux.just(
        ServerSentEvent.<String>builder()
                .data(JSONUtil.toJsonStr(Map.of("d", "{\"type\":\"error\",\"status\":\"duplicate_in_progress\"}")))
                .build(),
        ServerSentEvent.<String>builder()
                .event("done")
                .data("")
                .build()
);
```

If `REPLAY_SUCCESS`, return a short duplicate completed event and `done`.

For the first request, call:

```java
Flux<String> contentFlux = appService.chatToGenCode(appId, message, loginUser, requestId, idempotencyKey);
```

Mark success in `doOnComplete` and failure in `doOnError`.

- [ ] **Step 9: Run focused Java tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=AppControllerProductionBaselineTest,AppControllerTest,AppServiceImplProductionBaselineTest,PythonAiClientTest,IdempotencyServiceTest,AiGenerationPermitServiceTest
```

Expected: focused tests pass.

---

### Task 6: Python Internal Auth and Local Concurrency Guard

**Files:**
- Modify: `python-agent/config.py`
- Modify: `python-agent/server/main.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write failing Python tests**

```python
import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_health_does_not_require_internal_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "secret")
    import importlib
    import server.main as main
    importlib.reload(main)

    client = TestClient(main.app)
    response = client.get("/api/health")

    assert response.status_code == 200


def test_generate_code_rejects_missing_internal_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "secret")
    import importlib
    import server.main as main
    importlib.reload(main)

    client = TestClient(main.app)
    response = client.post("/api/generate-code", json={"prompt": "hello"})

    assert response.status_code == 401


def test_generate_code_accepts_valid_internal_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "secret")
    import importlib
    import server.main as main
    importlib.reload(main)

    async def fake_stream_workflow(**kwargs):
        yield '{"type":"done","status":"success","request_id":"req-1"}'

    client = TestClient(main.app)
    with patch.object(main, "stream_workflow", fake_stream_workflow):
        response = client.post(
            "/api/generate-code",
            headers={"X-Internal-Token": "secret", "X-Request-Id": "req-1"},
            json={"prompt": "hello", "requestId": "req-1"},
        )

    assert response.status_code == 200
```

- [ ] **Step 2: Run the Python test and verify it fails**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: tests fail because auth middleware and `requestId` are not implemented.

- [ ] **Step 3: Add Python config**

In `python-agent/config.py`, add:

```python
INTERNAL_API_TOKEN: str = os.getenv("INTERNAL_API_TOKEN", "")
AGENT_MAX_CONCURRENT_REQUESTS: int = int(os.getenv("AGENT_MAX_CONCURRENT_REQUESTS", "4"))
AGENT_OVERLOAD_STATUS_CODE: int = int(os.getenv("AGENT_OVERLOAD_STATUS_CODE", "429"))
```

- [ ] **Step 4: Add request id to `CodeGenRequest`**

In `server/main.py`, add:

```python
request_id: str = Field(default="", alias="requestId", description="gateway request id")
```

- [ ] **Step 5: Add internal-token middleware**

In `server/main.py`, add:

```python
PUBLIC_PATHS = {"/api/health", "/metrics"}

@app.middleware("http")
async def internal_token_auth(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or not config.INTERNAL_API_TOKEN:
        return await call_next(request)
    provided = request.headers.get("X-Internal-Token", "")
    if provided != config.INTERNAL_API_TOKEN:
        return JSONResponse({"detail": "unauthorized internal request"}, status_code=401)
    return await call_next(request)
```

Place it before or after logging middleware; both are acceptable as long as unauthorized requests are rejected before endpoint execution.

- [ ] **Step 6: Add semaphore around generation**

Near module globals:

```python
agent_semaphore = asyncio.Semaphore(config.AGENT_MAX_CONCURRENT_REQUESTS)
```

In `generate_code`, acquire before returning the stream:

```python
try:
    await asyncio.wait_for(agent_semaphore.acquire(), timeout=0)
except asyncio.TimeoutError:
    return JSONResponse(
        {
            "type": "error",
            "status": "overloaded",
            "message": "AI Agent capacity is full. Please retry later.",
            "request_id": request.request_id,
            "trace_id": resolved_trace_id,
        },
        status_code=config.AGENT_OVERLOAD_STATUS_CODE,
    )
```

Release in the existing `finally` block:

```python
agent_semaphore.release()
```

- [ ] **Step 7: Pass request id into SSE events**

When calling `stream_workflow`, pass `request_id=request.request_id` after updating the stream function signature in `python-agent/workflow/sse_stream.py`:

```python
async def stream_workflow(..., request_id: str = "") -> AsyncGenerator[str, None]:
```

Inside `_event`, include:

```python
payload = {"type": event_type, "timestamp": now, "trace_id": trace_id, "request_id": request_id}
```

- [ ] **Step 8: Run Python focused tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected: focused tests pass.

---

### Task 7: Harness Documentation and Verification

**Files:**
- Create: `docs/production-hardening-harness.md`
- Modify: `.planning/2026-06-30-production-hardening/progress.md`

- [ ] **Step 1: Create the harness documentation**

Create `docs/production-hardening-harness.md`:

```markdown
# Production Hardening Harness

This harness verifies the first production baseline without calling real LLM providers.

## Java Focused Tests

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=ProductionBaselinePropertiesTest,IdempotencyServiceTest,AiGenerationPermitServiceTest,PythonAiClientTest,AppControllerProductionBaselineTest,AppServiceImplProductionBaselineTest
```

Expected result: all listed tests pass.

## Python Focused Tests

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected result: all listed tests pass.

## Local Service Auth Smoke Check

Start Python with:

```powershell
cd python-agent
$env:INTERNAL_API_TOKEN='dev-secret'
$env:PYTHONPATH='.'
.venv/Scripts/python.exe server/main.py
```

Unauthenticated generation should fail:

```powershell
curl -i -X POST http://localhost:8000/api/generate-code -H "Content-Type: application/json" -d "{\"prompt\":\"hello\"}"
```

Authenticated generation should enter the normal SSE path:

```powershell
curl -i -X POST http://localhost:8000/api/generate-code -H "Content-Type: application/json" -H "X-Internal-Token: dev-secret" -H "X-Request-Id: smoke-1" -d "{\"prompt\":\"hello\",\"requestId\":\"smoke-1\"}"
```
```

- [ ] **Step 2: Run Java compile**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn compile -DskipTests
```

Expected: compile succeeds.

- [ ] **Step 3: Run Java focused tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test -Dtest=ProductionBaselinePropertiesTest,IdempotencyServiceTest,AiGenerationPermitServiceTest,PythonAiClientTest,AppControllerProductionBaselineTest,AppServiceImplProductionBaselineTest
```

Expected: focused tests pass. If a pre-existing unrelated Spring context test fails, record it in progress and keep the focused test evidence.

- [ ] **Step 4: Run Python focused tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected: focused tests pass. If pytest is unavailable in the local venv, record the missing dependency and run `python -m py_compile server/main.py workflow/sse_stream.py config.py`.

- [ ] **Step 5: Update planning progress**

Append to `.planning/2026-06-30-production-hardening/progress.md`:

```markdown
- Implemented route 1 production baseline: Java idempotency, global generation permits, Python client headers/timeouts, Python internal auth, Python local concurrency guard, and harness documentation.
- Verification: Java compile result: <actual result>.
- Verification: Java focused tests result: <actual result>.
- Verification: Python focused tests result: <actual result>.
```

---

## Plan Self-Review

- Spec coverage: idempotency, high concurrency, Java-to-Python auth, WebClient reliability, Python semaphore, and harness tests are covered.
- Scope control: full queue conversion, Kafka/RabbitMQ, full Agent sandboxing, and model HA expansion are intentionally excluded.
- Type consistency: `requestId`, `idempotencyKey`, `IdempotencyDecision`, `IdempotencyRecord`, and permit handle names are used consistently across tasks.
- Dirty worktree caution: every implementation task must inspect the current file before editing and avoid reverting user-owned changes.
