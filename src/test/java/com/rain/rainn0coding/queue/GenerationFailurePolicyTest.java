package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import static org.junit.jupiter.api.Assertions.*;

class GenerationFailurePolicyTest {
    @Test void infrastructureCauseOverridesRetryAndInputErrors() {
        assertEquals(GenerationFailurePolicy.Kind.INFRASTRUCTURE,GenerationFailurePolicy.classify(
                new IllegalStateException("wrapper",new DataAccessResourceFailureException("offline"))));
        assertEquals(GenerationFailurePolicy.Kind.INFRASTRUCTURE,GenerationFailurePolicy.classify(new BusinessException(ErrorCode.PYTHON_SERVICE_UNAUTHORIZED)));
        assertEquals(GenerationFailurePolicy.Kind.RETRY,GenerationFailurePolicy.classify(new BusinessException(ErrorCode.PYTHON_SERVICE_TIMEOUT)));
        assertEquals(GenerationFailurePolicy.Kind.TERMINAL,GenerationFailurePolicy.classify(new BusinessException(ErrorCode.NO_AUTH_ERROR)));
    }
    @Test void exponentialBackoffWithJitterIsAlwaysBounded() {
        var config=new GenerationQueueProperties();
        for(int attempt=0;attempt<30;attempt++) {
            long delay=GenerationFailurePolicy.delaySeconds(config,attempt);
            assertTrue(delay>=config.getRetryBaseSeconds()&&delay<=config.getRetryMaxSeconds());
        }
        assertEquals(60,GenerationFailurePolicy.delaySeconds(config,20));
        config.setLeaseSeconds(config.getHeartbeatSeconds()*2);assertThrows(IllegalArgumentException.class,config::validate);
    }
}
