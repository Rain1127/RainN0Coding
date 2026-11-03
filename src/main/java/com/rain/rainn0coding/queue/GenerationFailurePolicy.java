package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import org.springframework.dao.DataAccessException;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeoutException;

final class GenerationFailurePolicy {
    enum Kind { INFRASTRUCTURE, RETRY, TERMINAL }

    static Kind classify(Throwable error) {
        Kind kind=Kind.TERMINAL;
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof DataAccessException || cause instanceof WebClientRequestException)
                return Kind.INFRASTRUCTURE;
            if (cause instanceof BusinessException business) {
                int code = business.getCode();
                if (code == ErrorCode.PYTHON_SERVICE_UNAVAILABLE.getCode()
                        || code == ErrorCode.PYTHON_SERVICE_UNAUTHORIZED.getCode()) return Kind.INFRASTRUCTURE;
                if (code == ErrorCode.PYTHON_SERVICE_TIMEOUT.getCode()
                        || code == ErrorCode.AI_GENERATION_OVERLOADED.getCode()
                        || code == ErrorCode.CHAT_IN_PROGRESS.getCode()) kind=Kind.RETRY;
            }
            if (cause instanceof TimeoutException) kind=Kind.RETRY;
        }
        return kind;
    }

    static long delaySeconds(GenerationQueueProperties config, int retries) {
        long base = Math.min(config.getRetryMaxSeconds(),
                (long) config.getRetryBaseSeconds() * (1L << Math.min(retries, 20)));
        long room = Math.min(base / 2, config.getRetryMaxSeconds() - base);
        return base + (room == 0 ? 0 : ThreadLocalRandom.current().nextLong(room + 1));
    }

    private GenerationFailurePolicy() {}
}
