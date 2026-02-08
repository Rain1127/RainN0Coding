package com.yupi.yuaicodemother.ai;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.yupi.yuaicodemother.ai.guardrail.PromptSafetyInputGuardrail;
import com.yupi.yuaicodemother.ai.guardrail.RetryOutputGuardrail;
import com.yupi.yuaicodemother.ai.tools.*;
import com.yupi.yuaicodemother.config.RedisChatMemoryStoreConfig;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;
import com.yupi.yuaicodemother.service.ChatHistoryService;
import com.yupi.yuaicodemother.utils.SpringContextUtil;
import dev.langchain4j.community.store.memory.chat.redis.RedisChatMemoryStore;
import dev.langchain4j.data.message.ToolExecutionResultMessage;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.StreamingChatModel;
import dev.langchain4j.service.AiServices;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * @className: AiCodeGeneratorServiceFactory
 * @author: xxy-Rain
 * @date: 2026/1/10 15:22
 * @version: 1.0
 * @description: TODO
 * ai 代码生成服务工厂类
 */
@Configuration
@Slf4j
public class AiCodeGeneratorServiceFactory {

    @Resource(name = "openAiChatModel")
    private ChatModel chatModel;

    @Resource
    private RedisChatMemoryStore redisChatMemoryStore;

    @Resource
    private ChatHistoryService chatHistoryService;

    @Resource
    private ToolManager toolManager;


    /**
     * AI 服务实例缓存
     * 缓存策略：
     * - 最大缓存 1000 个实例
     * - 写入后 30 分钟过期
     * - 访问后 10 分钟过期
     */
    private final Cache<String, AiCodeGeneratorService> serviceCache = Caffeine.newBuilder()
            .maximumSize(1000)
            .expireAfterWrite(Duration.ofMinutes(30))
            .expireAfterAccess(Duration.ofMinutes(10))
            .removalListener((key, value, cause) -> {
                log.debug("AI 服务实例被移除，缓存键: {}, 原因: {}", key, cause);
            })
            .build();

    /**
     * 根据 appId 获取服务（带缓存）(兼容老逻辑)
     * @param appId 应用ID
     * @return ai 代码生成服务实例
     */
    public AiCodeGeneratorService getAiCodeGeneratorService(long appId) {
        //从缓存中获取服务实例，如果有，则通过APPID直接获取，否则创建新实例 有点像getOrDefault
        return getAiCodeGeneratorService(appId, CodeGenTypeEnum.HTML);
    }

    /**
     * 根据 appId 获取服务（带缓存）
     * @param appId 应用ID
     * @param codeGenType 代码生成类型
     * @return ai 代码生成服务实例
     */
    public AiCodeGeneratorService getAiCodeGeneratorService(long appId, CodeGenTypeEnum codeGenType) {
        String cacheKey = buildCacheKey(appId, codeGenType);
        //从缓存中获取服务实例，如果有，则通过APPID直接获取，否则创建新实例 有点像getOrDefault
        return serviceCache.get(cacheKey, key -> createAiCodeGeneratorService(appId, codeGenType));
    }

    /**
     * 创建新的 AI 服务实例
     * @param appId 应用ID
     * @param codeGenType 代码生成类型
     * @return ai 代码生成服务实例
     */
    private AiCodeGeneratorService createAiCodeGeneratorService(long appId, CodeGenTypeEnum codeGenType) {
        log.info("为 appId: {} 创建新的 AI 服务实例", appId);
        // 根据 appId 构建独立的对话记忆
        MessageWindowChatMemory chatMemory = MessageWindowChatMemory
                .builder()
                .id(appId)
                .chatMemoryStore(redisChatMemoryStore)
                .maxMessages(20)
                .build();
        //从数据库中加载对话历史到记忆中
        chatHistoryService.loadChatHistoryToMemory(appId, chatMemory, 20);
        return switch (codeGenType){
            //只要你在AIservice方法中加上了@ToolMemoryId，那么你在构造AIservice时，就必须要传入chatMemoryProvider
            case VUE_PROJECT -> {
                StreamingChatModel reasoningStreamingChatModel = SpringContextUtil.getBean("reasoningStreamingChatModelPrototype", StreamingChatModel.class);
                yield AiServices.builder(AiCodeGeneratorService.class)
                        .streamingChatModel(reasoningStreamingChatModel)
                        .chatMemoryProvider(memoryId -> chatMemory)
                        .tools(toolManager.getAllTools())
                        .hallucinatedToolNameStrategy(toolExecutionRequest -> ToolExecutionResultMessage.from(
                                toolExecutionRequest, "Error: there is no tool called " + toolExecutionRequest.name())
                        )
                        .maxSequentialToolsInvocations(20) // 最大连续调用工具次数
                        .inputGuardrails(new PromptSafetyInputGuardrail()) //添加输入护轨
//                        .outputGuardrails(new RetryOutputGuardrail()) //添加输出护轨
                        .build();
            }
            // 原生 HTML 模式和多文件模式共享相同的配置
            case HTML,MULTI_FILE-> {
                //多例模式StreamingChatModel
                StreamingChatModel openAiStreamingChatModel = SpringContextUtil.getBean("streamingChatModelPrototype", StreamingChatModel.class);
                yield AiServices.builder(AiCodeGeneratorService.class)
                        .chatModel(chatModel)
                        .streamingChatModel(openAiStreamingChatModel)
                        .chatMemory(chatMemory)
                        .inputGuardrails(new PromptSafetyInputGuardrail()) //添加输入护轨
//                        .outputGuardrails(new RetryOutputGuardrail()) //添加输出护轨
                        .build();
            }
            default ->
                    throw new BusinessException(ErrorCode.SYSTEM_ERROR,"不支持的代码生成类型" + codeGenType.getValue());
        };
    }


    /**
     * 创建 ai 代码生成服务
     * @return ai 代码生成服务
     */
    @Bean
    public AiCodeGeneratorService aiCodeGeneratorService() {
        return getAiCodeGeneratorService(0L);
    }

    /**
     * 构建缓存键
     * @param appId 应用ID
     * @param codeGenType 代码生成类型
     * @return 缓存键
     */
    private String buildCacheKey(long appId, CodeGenTypeEnum codeGenType) {
        return appId + "_" + codeGenType.getValue();
    }
}
