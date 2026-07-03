package com.rain.rainn0coding.idempotency;

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
