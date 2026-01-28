package com.yupi.yuaicodemother.ai;

import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import dev.langchain4j.service.SystemMessage;
import org.springframework.stereotype.Service;

/**
 * AI代码生成类型路由服务
 *
 * @author yupi
 */
@Service
public interface AiCodeGenTypeRoutingService {

    /**
     * 根据用户提示路由代码生成类型
     *
     * @param userPrompt 用户提示
     * @return 代码生成类型
     */
    @SystemMessage(fromResource = "prompt/codegen-routing-system-prompt.txt")
    CodeGenTypeEnum routeCodeGenType(String userPrompt);

}
