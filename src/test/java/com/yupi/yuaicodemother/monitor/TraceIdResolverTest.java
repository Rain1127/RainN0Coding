package com.yupi.yuaicodemother.monitor;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.TraceContext;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TraceIdResolverTest {

    @Test
    void resolveCurrentTraceIdUsesActiveSpanWhenPresent() {
        Tracer tracer = mock(Tracer.class);
        Span span = mock(Span.class);
        TraceContext traceContext = mock(TraceContext.class);

        when(tracer.currentSpan()).thenReturn(span);
        when(span.context()).thenReturn(traceContext);
        when(traceContext.traceId()).thenReturn("1234567890abcdef1234567890abcdef");

        TraceIdResolver resolver = new TraceIdResolver(tracer);

        assertThat(resolver.resolveCurrentTraceId())
                .isEqualTo("1234567890abcdef1234567890abcdef");
    }

    @Test
    void resolveCurrentTraceIdFallsBackToUuidWhenSpanIsMissing() {
        Tracer tracer = mock(Tracer.class);
        when(tracer.currentSpan()).thenReturn(null);

        TraceIdResolver resolver = new TraceIdResolver(tracer);

        assertThat(resolver.resolveCurrentTraceId())
                .matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
    }
}
