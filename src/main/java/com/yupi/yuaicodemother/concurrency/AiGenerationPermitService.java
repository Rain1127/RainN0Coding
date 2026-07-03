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
        validateProperties(properties);
        this.semaphore = redissonClient.getPermitExpirableSemaphore(PERMIT_KEY);
        this.properties = properties;
    }

    public PermitHandle tryAcquire() {
        try {
            syncSemaphorePermits();
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
            semaphore.tryRelease(handle.permitId());
        } catch (Exception e) {
            log.warn("Failed to release AI generation permit {}", handle.permitId(), e);
        }
    }

    private void syncSemaphorePermits() {
        int maxConcurrentRequests = properties.getMaxConcurrentRequests();
        if (!semaphore.trySetPermits(maxConcurrentRequests)
                && semaphore.getPermits() != maxConcurrentRequests) {
            semaphore.setPermits(maxConcurrentRequests);
        }
    }

    private void validateProperties(AiCodegenProperties properties) {
        if (properties.getMaxConcurrentRequests() <= 0) {
            throw new IllegalArgumentException("maxConcurrentRequests must be greater than 0");
        }
        if (properties.getPermitLeaseMinutes() <= 0) {
            throw new IllegalArgumentException("permitLeaseMinutes must be greater than 0");
        }
    }

    public record PermitHandle(boolean acquired, String permitId) {

        public static PermitHandle notAcquired() {
            return new PermitHandle(false, null);
        }
    }
}
