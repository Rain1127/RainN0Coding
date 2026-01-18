package com.yupi.yuaicodemother.core;

import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import jakarta.annotation.Resource;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.core.publisher.Flux;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AiCodeGeneratorFacadeTest {

    @Resource
    private AiCodeGeneratorFacade aiCodeGeneratorFacade;

    @Test
    void generateAndSaveCode() {
        File file = aiCodeGeneratorFacade.generateAndSaveCode("生成一个登录页面,不超过20行", CodeGenTypeEnum.HTML);
        Assertions.assertNotNull(file);
    }


    @Test
    void generateAndSaveCodeStream() {
        Flux<String> codeStream = aiCodeGeneratorFacade.generateAndSaveCodeStream("生成一个登录页面,不超过20行", CodeGenTypeEnum.HTML);
        //等所有流式输出完成，返回一个List。若没完成，则阻塞到完成。
        List<String> result = codeStream.collectList().block();
        //验证结果
        Assertions.assertFalse(result.isEmpty());
        //拼接字符串，得到完整内容.就是把集合里的元素拼接成一个字符串
        String completeContent = String.join("", result);
        Assertions.assertNotNull(completeContent);
    }
}