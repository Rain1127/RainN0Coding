package com.rain.rainn0coding.core;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/** Publish a validated candidate, retaining the previous directory and a recovery journal. */
public final class ArtifactPublisher {
    private ArtifactPublisher() {}

    public static Path candidate(Path current) throws IOException {
        recover(current);
        Path store = current.resolveSibling("." + current.getFileName() + ".versions");
        Files.createDirectories(store);
        return Files.createTempDirectory(store, "candidate-");
    }

    public static void recover(Path current) throws IOException {
        Path journal = current.resolveSibling("." + current.getFileName() + ".publishing");
        if (!Files.exists(journal)) return;
        Path backup = current.resolveSibling(Files.readString(journal));
        if (!backup.getParent().equals(current.getParent()) || !backup.getFileName().toString().startsWith("." + current.getFileName() + ".previous-"))
            throw new IOException("Invalid artifact recovery journal");
        if (!Files.exists(current) && Files.isDirectory(backup)) Files.move(backup, current);
        Files.deleteIfExists(journal);
    }

    public static void publish(Path current, Path candidate) throws IOException {
        Path backup = current.resolveSibling("." + current.getFileName() + ".previous-" + java.util.UUID.randomUUID());
        Path journal = current.resolveSibling("." + current.getFileName() + ".publishing");
        Path temp = Files.createTempFile(current.getParent(), ".publication-", ".tmp");
        Files.writeString(temp, backup.getFileName().toString());
        Files.move(temp, journal, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        try {
            if (Files.exists(current)) Files.move(current, backup);
            Files.move(candidate, current);
        } catch (IOException ex) {
            recover(current);
            throw ex;
        }
        Files.deleteIfExists(journal);
    }
}
