package com.yupi.yuaicodemother.monitor;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class TraceIdResolver {

    private final Tracer tracer;

    public TraceIdResolver(Tracer tracer) {
        this.tracer = tracer;
    }

    public String resolveCurrentTraceId() {
        if (tracer != null) {
            Span currentSpan = tracer.currentSpan();
            if (currentSpan != null && currentSpan.context() != null) {
                String traceId = currentSpan.context().traceId();
                if (traceId != null && !traceId.isBlank()) {
                    return traceId;
                }
            }
        }
        return UUID.randomUUID().toString();
    }
}
