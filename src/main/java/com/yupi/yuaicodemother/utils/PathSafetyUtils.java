package com.yupi.yuaicodemother.utils;

import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;

import java.nio.file.Path;

public final class PathSafetyUtils {

    private PathSafetyUtils() {
    }

    public static Path resolveInside(Path root, String... pathParts) {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        Path resolved = normalizedRoot;
        for (String part : pathParts) {
            if (part == null || part.isBlank()) {
                continue;
            }
            Path partPath = Path.of(part);
            for (Path segment : partPath) {
                if ("..".equals(segment.toString())) {
                    throw new BusinessException(ErrorCode.FORBIDDEN_ERROR, "路径不允许包含上级目录");
                }
            }
            resolved = resolved.resolve(part);
        }
        resolved = resolved.toAbsolutePath().normalize();
        if (!resolved.startsWith(normalizedRoot)) {
            throw new BusinessException(ErrorCode.FORBIDDEN_ERROR, "路径超出允许范围");
        }
        return resolved;
    }
}
