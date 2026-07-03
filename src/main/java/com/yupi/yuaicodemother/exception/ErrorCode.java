package com.yupi.yuaicodemother.exception;

import lombok.Getter;

@Getter
public enum ErrorCode {

    SUCCESS(0, "ok"),
    REQUEST_IN_PROGRESS(42902, "请求正在处理中"),
    REQUEST_REPLAY_CONFLICT(40900, "幂等键已被不同请求使用"),
    AI_GENERATION_OVERLOADED(42903, "AI 生成服务繁忙"),
    PYTHON_SERVICE_UNAUTHORIZED(50201, "Python Agent 鉴权失败"),
    PYTHON_SERVICE_TIMEOUT(50400, "Python Agent 响应超时"),
    PYTHON_SERVICE_UNAVAILABLE(50300, "Python Agent 暂不可用"),
    PARAMS_ERROR(40000, "请求参数错误"),
    TOO_MANY_REQUEST(42900, "请求过于频繁"),
    CHAT_IN_PROGRESS(42901, "当前应用正在对话中，请等待完成"),
    NOT_LOGIN_ERROR(40100, "未登录"),
    NO_AUTH_ERROR(40101, "无权限"),
    NOT_FOUND_ERROR(40400, "请求数据不存在"),
    FORBIDDEN_ERROR(40300, "禁止访问"),
    SYSTEM_ERROR(50000, "系统内部异常"),
    OPERATION_ERROR(50001, "操作失败");

    /**
     * 状态码
     */
    private final int code;

    /**
     * 信息
     */
    private final String message;

    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }

}
