package com.yupi.yuaicodemother.service;

import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.model.dto.chathistory.ChatHistoryQueryRequest;
import com.yupi.yuaicodemother.model.entity.ChatHistory;
import com.yupi.yuaicodemother.model.entity.User;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;

import java.time.LocalDateTime;

/**
 * 对话历史 服务层。
 *
 * @author <a>Rain</a>
 */
public interface ChatHistoryService extends IService<ChatHistory> {

    Page<ChatHistory> listAppChatHistoryByPage(Long appId, int pageSize,
                                               LocalDateTime lastCreateTime,
                                               User loginUser);

    /**
     * 加载应用的对话历史到记忆中
     * @param appId 应用id
     * @param chatMemory 记忆对象
     * @param maxCount 最大加载条数
     * @return 加载条数
     */
    int loadChatHistoryToMemory(Long appId, MessageWindowChatMemory chatMemory, int maxCount);

    /**
     * 构造查询请求
     * @param chatHistoryQueryRequest 对话历史查询条件
     * @return 查询包装器
     */
    QueryWrapper getQueryWrapper(ChatHistoryQueryRequest chatHistoryQueryRequest);

    /**
     * 添加对话消息
     * @param appId 应用id
     * @param message 消息
     * @param messageType 消息类型
     * @param userId 用户id
     * @return 是否成功
     */
    boolean addChatMessage(Long appId, String message,String messageType,Long userId);

     /**
     * 根据应用id删除对话历史
     * @param appId 应用id
     * @return 是否成功
     */
    boolean deleteByAppId(Long appId);
}
