package com.yupi.yuaicodemother.concurrency;

import com.yupi.yuaicodemother.config.AiCodegenProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RPermitExpirableSemaphore;
import org.redisson.api.RedissonClient;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
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
    void acquireDoesNotTreatAlreadyInitializedSemaphoreAsOverloaded() throws Exception {
        when(semaphore.trySetPermits(2)).thenReturn(false);
        when(semaphore.getPermits()).thenReturn(2);
        when(semaphore.tryAcquire(0, 30, TimeUnit.MINUTES)).thenReturn("permit-1");

        AiGenerationPermitService.PermitHandle handle = service.tryAcquire();

        assertThat(handle.acquired()).isTrue();
        assertThat(handle.permitId()).isEqualTo("permit-1");
        verify(semaphore, never()).setPermits(2);
    }

    @Test
    void acquireUpdatesPermitsWhenInitializedSemaphoreDiffersFromConfiguredMax() throws Exception {
        when(semaphore.trySetPermits(2)).thenReturn(false);
        when(semaphore.getPermits()).thenReturn(4);
        when(semaphore.tryAcquire(0, 30, TimeUnit.MINUTES)).thenReturn("permit-1");

        AiGenerationPermitService.PermitHandle handle = service.tryAcquire();

        assertThat(handle.acquired()).isTrue();
        verify(semaphore).setPermits(2);
    }

    @Test
    void acquireReturnsEmptyHandleWhenOverloaded() throws Exception {
        when(semaphore.trySetPermits(2)).thenReturn(false);
        when(semaphore.getPermits()).thenReturn(2);
        when(semaphore.tryAcquire(0, 30, TimeUnit.MINUTES)).thenReturn(null);

        AiGenerationPermitService.PermitHandle handle = service.tryAcquire();

        assertThat(handle.acquired()).isFalse();
    }

    @Test
    void constructorRejectsNonPositiveMaxConcurrentRequests() {
        AiCodegenProperties properties = properties(0, 30);
        RedissonClient redissonClient = mock(RedissonClient.class);

        assertThatThrownBy(() -> new AiGenerationPermitService(redissonClient, properties))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("maxConcurrentRequests");
    }

    @Test
    void constructorRejectsNonPositivePermitLeaseMinutes() {
        AiCodegenProperties properties = properties(2, 0);
        RedissonClient redissonClient = mock(RedissonClient.class);

        assertThatThrownBy(() -> new AiGenerationPermitService(redissonClient, properties))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("permitLeaseMinutes");
    }

    @Test
    void releaseUsesTryReleaseWithPermitId() {
        when(semaphore.tryRelease("permit-1")).thenReturn(true);
        AiGenerationPermitService.PermitHandle handle = new AiGenerationPermitService.PermitHandle(true, "permit-1");

        service.release(handle);

        verify(semaphore).tryRelease("permit-1");
        verify(semaphore, never()).release("permit-1");
    }

    @Test
    void releaseIgnoresNullAndNotAcquiredHandles() {
        service.release(null);
        service.release(AiGenerationPermitService.PermitHandle.notAcquired());
        service.release(new AiGenerationPermitService.PermitHandle(true, null));

        verifyNoInteractions(semaphore);
    }

    @Test
    void releaseTreatsTryReleaseFalseAsAlreadyReleased() {
        when(semaphore.tryRelease("permit-1")).thenReturn(false);
        AiGenerationPermitService.PermitHandle handle = new AiGenerationPermitService.PermitHandle(true, "permit-1");

        service.release(handle);

        verify(semaphore).tryRelease("permit-1");
        verify(semaphore, never()).release("permit-1");
    }

    private AiCodegenProperties properties(int maxConcurrentRequests, int permitLeaseMinutes) {
        AiCodegenProperties properties = new AiCodegenProperties();
        properties.setMaxConcurrentRequests(maxConcurrentRequests);
        properties.setPermitLeaseMinutes(permitLeaseMinutes);
        return properties;
    }
}
