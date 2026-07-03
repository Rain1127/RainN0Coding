package com.rain.rainn0coding.idempotency;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import java.time.Instant;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class IdempotencyRecord implements Serializable {

    private static final long serialVersionUID = 1L;

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
