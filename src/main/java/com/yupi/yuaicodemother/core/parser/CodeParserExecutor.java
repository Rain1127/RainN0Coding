package com.yupi.yuaicodemother.core.parser;


import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;

/**
 * 代码解析执行器
 *
 */
public class CodeParserExecutor {

    public static final HtmlCodeParser htmlCodeParser = new HtmlCodeParser();
    public static final MultiFileCodeParser multiFileCodeParser = new MultiFileCodeParser();
    /**
     *
     * @param codeContent 代码内容
     * @param codeGenTypeEnum 代码生成类型枚举
     * @return 解析后的代码 HtmlCodeResult or MultiFileCodeResult
     */
    public static Object executeParser(String codeContent, CodeGenTypeEnum codeGenTypeEnum){
        return switch (codeGenTypeEnum){
            case HTML -> htmlCodeParser.parseCode(codeContent);
            case MULTI_FILE -> multiFileCodeParser.parseCode(codeContent);
            default -> new BusinessException(ErrorCode.SYSTEM_ERROR,"不支持的代码生成类型");
        };
    }
}
