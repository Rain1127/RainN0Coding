package com.rain.rainn0coding.model.dto.app;

/** Identifies a generation without accepting client-provided ownership. */
public record GenerationControlRequest(Long appId, String runId) {
}
