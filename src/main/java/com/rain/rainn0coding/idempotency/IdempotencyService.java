package com.rain.rainn0coding.idempotency;

import cn.hutool.core.util.StrUtil;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.rain.rainn0coding.config.IdempotencyProperties;
import org.redisson.api.RBucket;
import org.redisson.api.RedissonClient;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Service
public class IdempotencyService {

    private final RedissonClient redissonClient;
    private final IdempotencyProperties properties;
    private final ObjectMapper objectMapper;

    public IdempotencyService(RedissonClient redissonClient, IdempotencyProperties properties) {
        this.redissonClient = redissonClient;
        this.properties = properties;
        this.objectMapper = new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY);
    }

    public IdempotencyDecision start(String operation, Long userId, String rawKey, String fingerprint, Duration processingTtl) {
        validateFingerprint(fingerprint);
        validateTtl(processingTtl);
        if (!properties.isEnabled() || StrUtil.isBlank(rawKey)) {
            return IdempotencyDecision.bypass();
        }
        String redisKey = redisKey(operation, userId, rawKey);
        RBucket<String> bucket = redissonClient.getBucket(redisKey);
        boolean claimed = bucket.trySet(toJson(IdempotencyRecord.processing(fingerprint)),
                processingTtl.toMillis(), TimeUnit.MILLISECONDS);
        if (claimed) {
            return IdempotencyDecision.of(IdempotencyDecision.Type.STARTED, redisKey, null);
        }
        IdempotencyRecord existing = fromJson(bucket.get());
        if (existing == null) {
            return IdempotencyDecision.of(IdempotencyDecision.Type.IN_PROGRESS, redisKey, null);
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
        validateFingerprint(fingerprint);
        if (StrUtil.isBlank(redisKey)) {
            return;
        }
        transitionProcessing(redisKey, fingerprint,
                IdempotencyRecord.success(fingerprint, resultJson, httpStatus), properties.successTtl());
    }

    public void markFailed(String redisKey, String fingerprint, int errorCode, String errorMessage) {
        validateFingerprint(fingerprint);
        if (StrUtil.isBlank(redisKey)) {
            return;
        }
        transitionProcessing(redisKey, fingerprint,
                IdempotencyRecord.failed(fingerprint, errorCode, errorMessage), properties.failureTtl());
    }

    public String fingerprint(String operation, Object... parts) {
        List<FingerprintEntry> entries = new ArrayList<>();
        entries.add(new FingerprintEntry("operation", operation));
        for (Object part : parts) {
            entries.add(new FingerprintEntry(part == null ? "null" : part.getClass().getName(), canonicalValue(part)));
        }
        return sha256(toJson(entries));
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

    private void transitionProcessing(String redisKey, String fingerprint, IdempotencyRecord nextRecord, Duration ttl) {
        validateTtl(ttl);
        RBucket<String> bucket = redissonClient.getBucket(redisKey);
        String existingJson = bucket.get();
        IdempotencyRecord existing = fromJson(existingJson);
        if (existing == null
                || existing.getStatus() != IdempotencyStatus.PROCESSING
                || !fingerprint.equals(existing.getFingerprint())) {
            return;
        }
        if (bucket.compareAndSet(existingJson, toJson(nextRecord))) {
            bucket.expire(ttl);
        }
    }

    private void validateFingerprint(String fingerprint) {
        if (StrUtil.isBlank(fingerprint)) {
            throw new IllegalArgumentException("idempotency fingerprint must not be blank");
        }
    }

    private void validateTtl(Duration ttl) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("idempotency ttl must be positive");
        }
    }

    private String canonicalValue(Object part) {
        if (part == null) {
            return null;
        }
        if (part instanceof CharSequence || part instanceof Number || part instanceof Boolean || part instanceof Enum<?>) {
            return String.valueOf(part);
        }
        return toJson(part);
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Unable to serialize idempotency value", e);
        }
    }

    private IdempotencyRecord fromJson(String json) {
        if (StrUtil.isBlank(json)) {
            return null;
        }
        try {
            return objectMapper.readValue(json, IdempotencyRecord.class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Unable to parse idempotency record", e);
        }
    }

    private record FingerprintEntry(String type, String value) {
    }
}
