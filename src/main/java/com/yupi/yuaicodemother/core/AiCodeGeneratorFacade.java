package com.yupi.yuaicodemother.core;

import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.constant.AppConstant;
import com.yupi.yuaicodemother.core.builder.VueProjectBuilder;
import com.yupi.yuaicodemother.core.python.PythonAiClient;
import com.yupi.yuaicodemother.core.saver.CodeFileSaverExecutor;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.monitor.MonitorContextHolder;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * 代码生成门面 —— 委托给 Python AI Agent（7-Agent + RAG）。
 *
 * Java 侧不再直接调用 DeepSeek/LangChain4j。
 * 重构日期: 2026-05-24
 */
@Service
@Slf4j
public class AiCodeGeneratorFacade {

    @Resource
    private VueProjectBuilder vueProjectBuilder;

    @Resource
    private PythonAiClient pythonAiClient;

    /**
     * 流式代码生成 —— 透传 Python SSE 事件到前端。
     *
     * Python 返回的是 SSE 事件行 (data: {...})。
     * 前端通过 EventSource 解析 JSON 事件，展示各阶段进度。
     *
     * @param userMessage     用户提示词
     * @param codeGenTypeEnum 代码生成类型
     * @param appId           应用 ID
     * @return SSE 事件 Flux
     */
    public Flux<String> generateAndSaveCodeStream(String userMessage,
                                                   CodeGenTypeEnum codeGenTypeEnum,
                                                   Long appId,
                                                   Long userId,
                                                   String userRole) {
        if (codeGenTypeEnum == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "代码生成类型不能为空");
        }

        String traceId = MonitorContextHolder.getContext().getTraceId();
        log.info("透传 traceId 到 Python Agent: {}", traceId);

        Flux<String> sseStream = pythonAiClient.streamCodeGen(
                String.valueOf(userId), String.valueOf(appId), userMessage,
                codeGenTypeEnum.getValue(), userRole, traceId);

        // 收集 code_file 事件中的文件，流完成后保存
        List<CodeFileSaverExecutor.CodeFileDto> codeFiles = new ArrayList<>();

        return sseStream.doOnNext(line -> {
            // 提取 code_file 事件中的文件信息
            if (line != null && line.contains("\"code_file\"")) {
                try {
                    // SSE 格式: data: {"type":"code_file","path":"...","content":"..."}
                    String json = extractJson(line);
                    if (json != null) {
                        JSONObject obj = JSONUtil.parseObj(json);
                        if ("code_file".equals(obj.getStr("type"))) {
                            String path = obj.getStr("path");
                            String content = obj.getStr("content");
                            if (path != null && content != null) {
                                codeFiles.add(new CodeFileSaverExecutor.CodeFileDto(path, content));
                            }
                        }
                    }
                } catch (Exception e) {
                    log.debug("解析 code_file 事件失败: {}", e.getMessage());
                }
            }
        }).doOnComplete(() -> {
            if (!codeFiles.isEmpty()) {
                try {
                    File saveDir = CodeFileSaverExecutor.executeSaver(
                            codeFiles, codeGenTypeEnum, appId);
                    log.info("代码已保存: {} 个文件, 目录 {}", codeFiles.size(), saveDir);
                } catch (Exception e) {
                    log.error("代码保存失败: {}", e.getMessage());
                }
            }
            // 前端工程类型执行 npm build
            if (codeGenTypeEnum == CodeGenTypeEnum.VUE_PROJECT
                    || codeGenTypeEnum == CodeGenTypeEnum.NODEJS) {
                String dirName = codeGenTypeEnum.getValue().toLowerCase();
                try {
                    String projectPath = AppConstant.CODE_OUTPUT_ROOT_DIR
                            + "/" + dirName + "_" + appId;
                    vueProjectBuilder.buildProject(projectPath);
                } catch (Exception e) {
                    log.error("{} 项目构建失败: {}", dirName, e.getMessage());
                }
            }
            // 后端语言 (PYTHON/JAVA/GO/RUST/GENERIC) 跳过构建，只保存源码
        }).doOnError(e -> log.error("Python Agent 调用失败: {}", e.getMessage()));
    }

    /**
     * 同步代码生成（保留接口兼容，实际委托流式方法）。
     */
    public File generateAndSaveCode(String userMessage, CodeGenTypeEnum codeGenTypeEnum, Long appId) {
        throw new BusinessException(ErrorCode.SYSTEM_ERROR,
                "同步代码生成已废弃，请使用 SSE 流式端点");
    }

    // ---- 内部工具 ----

    private String extractJson(String sseLine) {
        // SSE 格式: "data: {...}"
        if (sseLine.startsWith("data: ")) {
            return sseLine.substring(6);
        }
        if (sseLine.startsWith("data:")) {
            return sseLine.substring(5);
        }
        return sseLine;
    }
}
