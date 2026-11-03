package com.rain.rainn0coding.controller;

import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.service.AppService;
import com.rain.rainn0coding.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** Owner-scoped gateway for Python's durable execution evidence. */
@RestController
@RequestMapping("/app/chat/gen")
public class GenerationHarnessController {
    private final AppService apps;
    private final UserService users;
    private final PythonAiClient python;

    public GenerationHarnessController(AppService apps, UserService users, PythonAiClient python) {
        this.apps = apps;
        this.users = users;
        this.python = python;
    }

    private long owner(long appId, String runId, HttpServletRequest request) {
        if (appId <= 0 || runId == null || runId.isBlank() || runId.length() > 128) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        long userId = users.getLoginUser(request).getId();
        var app = apps.getById(appId);
        if (app == null) throw new BusinessException(ErrorCode.NOT_FOUND_ERROR);
        if (!Objects.equals(app.getUserId(), userId)) throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        return userId;
    }

    @GetMapping("/steps")
    public BaseResponse<Map<String, Object>> steps(@RequestParam long appId, @RequestParam String runId,
            @RequestParam(defaultValue = "0") long after, @RequestParam(defaultValue = "100") int limit,
            HttpServletRequest request) {
        long userId = owner(appId, runId, request);
        if (after < 0 || limit < 1 || limit > 200) throw new BusinessException(ErrorCode.PARAMS_ERROR);
        return ResultUtils.success(python.generationEvents(String.valueOf(userId), String.valueOf(appId), runId, after, limit));
    }

    @GetMapping("/instructions")
    public BaseResponse<Map<String, Object>> instructions(@RequestParam long appId, @RequestParam String runId,
            HttpServletRequest request) {
        long userId = owner(appId, runId, request);
        return ResultUtils.success(python.generationInstructions(Map.of(
                "userId", String.valueOf(userId), "appId", String.valueOf(appId), "runId", runId, "action", "list")));
    }

    public record InstructionAction(long appId, String runId, UUID instructionId, String action, String target, String content) {}

    @PostMapping("/instructions")
    public BaseResponse<Map<String, Object>> instruction(@RequestBody InstructionAction action,
            HttpServletRequest request) {
        if (action == null || action.instructionId() == null
                || !("submit".equals(action.action()) || "cancel".equals(action.action()))) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR);
        }
        long userId = owner(action.appId(), action.runId(), request);
        Map<String, Object> payload = new HashMap<>(Map.of(
                "userId", String.valueOf(userId), "appId", String.valueOf(action.appId()), "runId", action.runId(),
                "instructionId", action.instructionId().toString(), "action", action.action()));
        if ("submit".equals(action.action())) {
            if (!("next_step".equals(action.target()) || "next_run".equals(action.target()))
                    || action.content() == null || action.content().isBlank() || action.content().length() > 1200) {
                throw new BusinessException(ErrorCode.PARAMS_ERROR);
            }
            payload.put("target", action.target());
            payload.put("content", action.content());
        }
        return ResultUtils.success(python.generationInstructions(payload));
    }
}
