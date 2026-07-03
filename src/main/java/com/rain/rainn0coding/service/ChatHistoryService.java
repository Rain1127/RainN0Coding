package com.rain.rainn0coding.service;

import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.core.service.IService;
import com.rain.rainn0coding.model.dto.chathistory.ChatHistoryQueryRequest;
import com.rain.rainn0coding.model.entity.ChatHistory;
import com.rain.rainn0coding.model.entity.User;

import java.time.LocalDateTime;

/**
 * 对话历史服务层
 *
 * @author <a>Rain</a>
 */
public interface ChatHistoryService extends IService<ChatHistory> {

    Page<ChatHistory> listAppChatHistoryByPage(Long appId, int pageSize,
                                               LocalDateTime lastCreateTime,
                                               User loginUser);

    QueryWrapper getQueryWrapper(ChatHistoryQueryRequest chatHistoryQueryRequest);

    boolean addChatMessage(Long appId, String message, String messageType, Long userId);

    boolean deleteByAppId(Long appId);
}
