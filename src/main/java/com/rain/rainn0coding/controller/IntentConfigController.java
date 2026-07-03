package com.rain.rainn0coding.controller;

import com.rain.rainn0coding.annotation.AuthCheck;
import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.constant.UserConstant;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.IntentConfigService;
import com.rain.rainn0coding.service.UserService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 意图树配置 —— 管理员自定义意图分类树。
 */
@RestController
@RequestMapping("/intent-config")
public class IntentConfigController {

    @Resource
    private IntentConfigService intentConfigService;

    @Resource
    private UserService userService;

    /**
     * 获取当前生效的意图树（管理员自定义 → 默认）
     */
    @GetMapping("/tree")
    public BaseResponse<Map<String, Object>> getTree() {
        String json = intentConfigService.getActiveTreeJson();
        return ResultUtils.success(Map.of(
                "customized", json != null,
                "treeJson", json != null ? json : ""
        ));
    }

    /**
     * 管理员保存自定义意图树。
     */
    @PostMapping("/save")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<?> saveTree(@RequestBody Map<String, String> body,
                                    HttpServletRequest request) {
        String treeJson = body.get("treeJson");
        if (treeJson == null || treeJson.isBlank()) {
            return ResultUtils.error(ErrorCode.PARAMS_ERROR, "treeJson 不能为空");
        }
        User loginUser = userService.getLoginUser(request);
        intentConfigService.saveCustomTree(treeJson, loginUser.getId());
        return ResultUtils.success(true);
    }

    /**
     * 重置为默认意图树（删除自定义配置）。
     */
    @PostMapping("/reset")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public BaseResponse<?> resetTree() {
        intentConfigService.saveCustomTree("", 0L);
        return ResultUtils.success(true);
    }
}
