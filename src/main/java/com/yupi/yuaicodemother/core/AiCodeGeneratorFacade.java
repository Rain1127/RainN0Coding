package com.yupi.yuaicodemother.core;

import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.constant.AppConstant;
import com.yupi.yuaicodemother.core.builder.VueProjectBuilder;
import com.yupi.yuaicodemother.core.python.PythonAiClient;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import com.yupi.yuaicodemother.monitor.MonitorContext;
import com.yupi.yuaicodemother.monitor.MonitorContextHolder;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

@Service
@Slf4j
public class AiCodeGeneratorFacade {

    @Resource
    private VueProjectBuilder vueProjectBuilder;

    @Resource
    private PythonAiClient pythonAiClient;

    public Flux<String> generateAndSaveCodeStream(String userMessage,
                                                  CodeGenTypeEnum codeGenTypeEnum,
                                                  Long appId,
                                                  Long userId,
                                                  String userRole) {
        return generateAndSaveCodeStream(userMessage, codeGenTypeEnum, appId, userId, userRole, null, null);
    }

    public Flux<String> generateAndSaveCodeStream(String userMessage,
                                                  CodeGenTypeEnum codeGenTypeEnum,
                                                  Long appId,
                                                  Long userId,
                                                  String userRole,
                                                  String requestId,
                                                  String idempotencyKey) {
        if (codeGenTypeEnum == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "code generation type cannot be null");
        }

        MonitorContext context = MonitorContextHolder.getContext();
        String traceId = context != null ? context.getTraceId() : null;
        if (traceId != null) {
            log.info("Pass traceId to Python Agent: {}", traceId);
        }

        Flux<String> sseStream = pythonAiClient.streamCodeGen(
                String.valueOf(userId), String.valueOf(appId), userMessage,
                codeGenTypeEnum.getValue(), userRole, traceId, requestId, idempotencyKey);

        List<CodeFileDto> codeFiles = new ArrayList<>();
        AtomicReference<String> terminalStatus = new AtomicReference<>();

        return sseStream.doOnNext(line -> {
            JSONObject obj = parseSseJson(line);
            if (obj == null) {
                return;
            }
            String type = obj.getStr("type");
            if ("error".equals(type)) {
                terminalStatus.compareAndSet(null, "error");
                return;
            }
            if ("done".equals(type)) {
                terminalStatus.updateAndGet(current -> current != null && !"success".equals(current)
                        ? current
                        : successfulStatus(obj.getStr("status")));
                return;
            }
            if ("code_file".equals(type)) {
                String path = obj.getStr("path");
                String content = obj.getStr("content");
                if (path != null && content != null) {
                    codeFiles.add(new CodeFileDto(path, content));
                }
            }
        })
                .concatWith(Mono.fromRunnable(() -> finalizeGeneratedCode(
                                codeFiles, codeGenTypeEnum, appId, terminalStatus.get()))
                        .then(Mono.empty()))
                .doOnError(e -> log.error("Python Agent code generation failed: {}", e.getMessage()));
    }

    private File saveCodeFiles(List<CodeFileDto> files, CodeGenTypeEnum codeGenType, Long appId) {
        Path basePath = Path.of(resolveBaseDir(codeGenType, appId)).toAbsolutePath().normalize();
        createDirectories(basePath, "create output directory");
        for (CodeFileDto file : files) {
            Path outPath = basePath.resolve(file.path()).normalize();
            if (!outPath.startsWith(basePath)) {
                throw new BusinessException(ErrorCode.PARAMS_ERROR,
                        "Invalid generated file path: " + file.path());
            }
            Path parentPath = outPath.getParent();
            if (parentPath != null) {
                createDirectories(parentPath, "create parent directory");
            }
            writeFile(outPath, file);
        }
        return basePath.toFile();
    }

    private void finalizeGeneratedCode(List<CodeFileDto> codeFiles, CodeGenTypeEnum codeGenTypeEnum,
                                       Long appId, String terminalStatus) {
        if (terminalStatus != null && !"success".equals(terminalStatus)) {
            log.warn("Skip code save/build because Python workflow ended with status: {}", terminalStatus);
            return;
        }
        if (!codeFiles.isEmpty()) {
            File saveDir = saveCodeFiles(codeFiles, codeGenTypeEnum, appId);
            log.info("Saved {} files to {}", codeFiles.size(), saveDir);
        }

        if (codeGenTypeEnum == CodeGenTypeEnum.VUE_PROJECT
                || codeGenTypeEnum == CodeGenTypeEnum.NODEJS) {
            String dirName = codeGenTypeEnum.getValue().toLowerCase();
            String projectPath = AppConstant.CODE_OUTPUT_ROOT_DIR + "/" + dirName + "_" + appId;
            boolean buildSuccess = vueProjectBuilder.buildProject(projectPath);
            if (!buildSuccess) {
                throw new BusinessException(ErrorCode.OPERATION_ERROR,
                        dirName + " project build failed");
            }
        }
    }

    private void createDirectories(Path path, String operation) {
        try {
            Files.createDirectories(path);
        } catch (IOException e) {
            throw new BusinessException(ErrorCode.SYSTEM_ERROR,
                    operation + " failed: " + path + " - " + e.getMessage());
        }
    }

    private void writeFile(Path outPath, CodeFileDto file) {
        try {
            Files.writeString(outPath, file.content());
        } catch (IOException e) {
            throw new BusinessException(ErrorCode.SYSTEM_ERROR,
                    "save file failed: " + file.path() + " - " + e.getMessage());
        }
    }

    private String resolveBaseDir(CodeGenTypeEnum codeGenType, Long appId) {
        String prefix = AppConstant.CODE_OUTPUT_ROOT_DIR;
        return switch (codeGenType) {
            case VUE_PROJECT -> prefix + "/vue_project_" + appId;
            case NODEJS -> prefix + "/nodejs_" + appId;
            case PYTHON -> prefix + "/python_" + appId;
            case JAVA -> prefix + "/java_" + appId;
            case GO -> prefix + "/go_" + appId;
            case RUST -> prefix + "/rust_" + appId;
            case HTML, MULTI_FILE, GENERIC -> prefix + "/" + codeGenType.getValue().toLowerCase() + "_" + appId;
        };
    }

    private String extractJson(String sseLine) {
        if (sseLine == null) {
            return null;
        }
        if (sseLine.startsWith("data: ")) {
            return sseLine.substring(6);
        }
        if (sseLine.startsWith("data:")) {
            return sseLine.substring(5);
        }
        return sseLine;
    }

    private JSONObject parseSseJson(String sseLine) {
        try {
            String json = extractJson(sseLine);
            if (json == null || !json.trim().startsWith("{")) {
                return null;
            }
            return JSONUtil.parseObj(json);
        } catch (Exception e) {
            log.debug("Failed to parse Python Agent event: {}", e.getMessage());
            return null;
        }
    }

    private String successfulStatus(String status) {
        if (status == null || status.isBlank()) {
            return "success";
        }
        return status;
    }

    private record CodeFileDto(String path, String content) {}
}
