package com.yupi.yuaicodemother.core.saver;

import com.yupi.yuaicodemother.ai.model.HtmlCodeResult;
import com.yupi.yuaicodemother.ai.model.MultiFileCodeResult;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * 代码文件保存执行器
 *
 * @author yupi
 */
public class CodeFileSaverExecutor {

    private static final HtmlCodeFileSaverTemplate htmlCodeFileSaver = new HtmlCodeFileSaverTemplate();

    private static final MultiFileCodeFileSaverTemplate multiFileCodeFileSaver = new MultiFileCodeFileSaverTemplate();

    /**
     * 执行代码保存（旧版 LangChain4j 路径，已废弃）
     */
    @Deprecated
    public static File executeSaver(Object codeResult, CodeGenTypeEnum codeGenType, Long appid) {
        return switch (codeGenType) {
            case HTML -> htmlCodeFileSaver.saveCode((HtmlCodeResult) codeResult, appid);
            case MULTI_FILE -> multiFileCodeFileSaver.saveCode((MultiFileCodeResult) codeResult, appid);
            default -> throw new BusinessException(ErrorCode.SYSTEM_ERROR, "不支持的代码生成类型: " + codeGenType);
        };
    }

    /**
     * 保存 Python Agent 返回的代码文件列表（新版）。
     *
     * @param files       [{path, content}] 代码文件列表
     * @param codeGenType 代码生成类型
     * @param appId       应用 ID
     * @return 保存的基础目录
     */
    public static File executeSaver(List<CodeFileDto> files, CodeGenTypeEnum codeGenType, Long appId) {
        String prefix = com.yupi.yuaicodemother.constant.AppConstant.CODE_OUTPUT_ROOT_DIR;
        String baseDir = switch (codeGenType) {
            case VUE_PROJECT  -> prefix + "/vue_project_" + appId;
            case NODEJS       -> prefix + "/nodejs_" + appId;
            case PYTHON       -> prefix + "/python_" + appId;
            case JAVA         -> prefix + "/java_" + appId;
            case GO           -> prefix + "/go_" + appId;
            case RUST         -> prefix + "/rust_" + appId;
            case HTML, MULTI_FILE, GENERIC -> prefix + "/" + codeGenType.getValue().toLowerCase() + "_" + appId;
        };

        File baseDirFile = new File(baseDir);
        if (!baseDirFile.exists()) {
            baseDirFile.mkdirs();
        }

        for (CodeFileDto f : files) {
            File outFile = new File(baseDirFile, f.path());
            outFile.getParentFile().mkdirs();
            try (FileWriter writer = new FileWriter(outFile)) {
                writer.write(f.content());
            } catch (IOException e) {
                throw new BusinessException(ErrorCode.SYSTEM_ERROR,
                        "保存文件失败: " + f.path() + " - " + e.getMessage());
            }
        }

        return baseDirFile;
    }

    /**
     * 代码文件 DTO（path + content）。
     */
    public record CodeFileDto(String path, String content) {}
}
