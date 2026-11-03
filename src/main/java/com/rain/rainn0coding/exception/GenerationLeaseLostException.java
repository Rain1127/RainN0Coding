package com.rain.rainn0coding.exception;

/** The current execution no longer has permission to publish effects or results. */
public class GenerationLeaseLostException extends IllegalStateException {
    public GenerationLeaseLostException() {super("Generation execution lease lost");}
}
