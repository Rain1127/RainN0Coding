package com.rain.rainn0coding.controller;

import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.rain.rainn0coding.annotation.AuthCheck;
import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.constant.UserConstant;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.exception.ThrowUtils;
import com.rain.rainn0coding.model.dto.chathistory.ChatHistoryQueryRequest;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.ratelimiter.annotation.RateLimit;
import com.rain.rainn0coding.ratelimiter.enums.RateLimitType;
import com.rain.rainn0coding.service.UserService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.rain.rainn0coding.model.entity.ChatHistory;
import com.rain.rainn0coding.service.ChatHistoryService;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 对话历史 控制层。
 *
 * @author <a>Rain</a>
 */
@RestController
@RequestMapping("/chatHistory")
public class ChatHistoryController {

    private static final long MAX_PAGE_SIZE = 50;

    @Resource
    private ChatHistoryService chatHistoryService;

    @Resource
    private UserService userService;

    /**
     * 分页查询某个应用的对话历史（游标查询）
     *
     * @param appId          应用ID
     * @param pageSize       页面大小
     * @param lastCreateTime 最后一条记录的创建时间
     * @param request        请求
     * @return 对话历史分页
     */
    @GetMapping("/app/{appId}")
    @RateLimit(limitType = RateLimitType.USER, rate = 30, rateInterval = 60, message = "查询过于频繁，请稍后再试")
    public BaseResponse<Page<ChatHistory>> listAppChatHistory(@PathVariable Long appId,
                                                              @RequestParam(defaultValue = "10") int pageSize,
                                                              @RequestParam(required = false) LocalDateTime lastCreateTime,
                                                              HttpServletRequest request) {
        User loginUser = userService.getLoginUser(request);
        Page<ChatHistory> result = chatHistoryService.listAppChatHistoryByPage(appId, pageSize, lastCreateTime, loginUser);
        return ResultUtils.success(result);
    }

    /**
     * 管理员分页查询所有对话历史
     *
     * @param chatHistoryQueryRequest 查询请求
     * @return 对话历史分页
     */
    @PostMapping("/admin/list/page/vo")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<Page<ChatHistory>> listAllChatHistoryByPageForAdmin(@RequestBody ChatHistoryQueryRequest chatHistoryQueryRequest) {
        ThrowUtils.throwIf(chatHistoryQueryRequest == null, ErrorCode.PARAMS_ERROR);
        long pageNum = chatHistoryQueryRequest.getPageNum();
        long pageSize = chatHistoryQueryRequest.getPageSize();
        ThrowUtils.throwIf(pageSize <= 0 || pageSize > MAX_PAGE_SIZE, ErrorCode.PARAMS_ERROR, "每页最多查询 50 条记录");
        // 查询数据
        QueryWrapper queryWrapper = chatHistoryService.getQueryWrapper(chatHistoryQueryRequest);
        Page<ChatHistory> result = chatHistoryService.page(Page.of(pageNum, pageSize), queryWrapper);
        return ResultUtils.success(result);
    }

}
