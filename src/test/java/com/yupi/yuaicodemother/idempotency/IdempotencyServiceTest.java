package com.yupi.yuaicodemother.idempotency;

import com.yupi.yuaicodemother.config.IdempotencyProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RBucket;
import org.redisson.api.RedissonClient;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IdempotencyServiceTest {

    private RedissonClient redissonClient;
    private RBucket<String> bucket;
    private IdempotencyService idempotencyService;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        redissonClient = mock(RedissonClient.class);
        bucket = mock(RBucket.class);
        when(redissonClient.<String>getBucket(anyString())).thenReturn(bucket);
        idempotencyService = new IdempotencyService(redissonClient, new IdempotencyProperties());
    }

    @Test
    void blankKeyBypassesIdempotency() {
        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.BYPASS);
    }

    @Test
    void missingRecordStartsProcessingWithAtomicTrySet() {
        Duration ttl = Duration.ofMinutes(1);
        when(bucket.trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS))).thenReturn(true);

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", ttl);

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.STARTED);
        verify(bucket).trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS));
        verify(bucket, never()).set(anyString(), any(Duration.class));
        verify(bucket, never()).get();
    }

    @Test
    void duplicateClaimReadsExistingJsonWhenTrySetReturnsFalse() {
        when(bucket.trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS))).thenReturn(false);
        when(bucket.get()).thenReturn(processingJson("fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.IN_PROGRESS);
        assertThat(decision.record().getStatus()).isEqualTo(IdempotencyStatus.PROCESSING);
        assertThat(decision.record().getFingerprint()).isEqualTo("fp");
    }

    @Test
    void fingerprintMismatchIsConflict() {
        when(bucket.trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS))).thenReturn(false);
        when(bucket.get()).thenReturn(processingJson("other-fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.FINGERPRINT_MISMATCH);
    }

    @Test
    void successRecordIsReplayable() {
        when(bucket.trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS))).thenReturn(false);
        when(bucket.get()).thenReturn(successJson("fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.REPLAY_SUCCESS);
        assertThat(decision.record().getResultJson()).isEqualTo("{\"data\":123}");
    }

    @Test
    void processingRecordRejectsDuplicate() {
        when(bucket.trySet(anyString(), eq(60000L), eq(TimeUnit.MILLISECONDS))).thenReturn(false);
        when(bucket.get()).thenReturn(processingJson("fp"));

        IdempotencyDecision decision = idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofMinutes(1));

        assertThat(decision.type()).isEqualTo(IdempotencyDecision.Type.IN_PROGRESS);
    }

    @Test
    void markSuccessOnlyTransitionsProcessingRecordWithSameFingerprint() {
        String existingJson = processingJson("fp");
        when(bucket.get()).thenReturn(existingJson);
        when(bucket.compareAndSet(eq(existingJson), anyString())).thenReturn(true);

        idempotencyService.markSuccess("idempotency:key", "fp", "{\"ok\":true}", 201);

        verify(bucket).compareAndSet(eq(existingJson), anyString());
        verify(bucket).expire(Duration.ofHours(24));
        verify(bucket, never()).set(anyString(), any(Duration.class));
    }

    @Test
    void markSuccessDoesNotOverwriteSuccessOrMismatchedFingerprint() {
        when(bucket.get()).thenReturn(successJson("fp"), processingJson("other-fp"));

        idempotencyService.markSuccess("idempotency:key", "fp", "{\"ok\":true}", 200);
        idempotencyService.markSuccess("idempotency:key", "fp", "{\"ok\":true}", 200);

        verify(bucket, never()).compareAndSet(anyString(), anyString());
        verify(bucket, never()).set(anyString(), any(Duration.class));
        verify(bucket, never()).expire(any(Duration.class));
    }

    @Test
    void startRejectsBlankFingerprintAndInvalidTtl() {
        assertThatThrownBy(() -> idempotencyService.start("app:add", 1L, "key-1", " ", Duration.ofMinutes(1)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> idempotencyService.start("app:add", 1L, "key-1", null, Duration.ofMinutes(1)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> idempotencyService.start("app:add", 1L, "key-1", "fp", null))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ZERO))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> idempotencyService.start("app:add", 1L, "key-1", "fp", Duration.ofSeconds(-1)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void fingerprintDistinguishesAmbiguousPartLists() {
        String first = idempotencyService.fingerprint("op", "a\nb", "c");
        String second = idempotencyService.fingerprint("op", "a", "b\nc");

        assertThat(first).isNotEqualTo(second);
    }

    private String processingJson(String fingerprint) {
        return "{\"status\":\"PROCESSING\",\"fingerprint\":\"" + fingerprint + "\",\"resultJson\":null,\"httpStatus\":null,"
                + "\"errorCode\":null,\"errorMessage\":null,\"createdAt\":\"2026-01-01T00:00:00Z\","
                + "\"updatedAt\":\"2026-01-01T00:00:00Z\"}";
    }

    private String successJson(String fingerprint) {
        return "{\"status\":\"SUCCESS\",\"fingerprint\":\"" + fingerprint + "\",\"resultJson\":\"{\\\"data\\\":123}\","
                + "\"httpStatus\":200,\"errorCode\":null,\"errorMessage\":null,\"createdAt\":\"2026-01-01T00:00:00Z\","
                + "\"updatedAt\":\"2026-01-01T00:00:00Z\"}";
    }
}
