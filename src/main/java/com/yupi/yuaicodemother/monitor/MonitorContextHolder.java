package com.yupi.yuaicodemother.monitor;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public class MonitorContextHolder {

    private static final ThreadLocal<MonitorContext> CONTEXT_HOLDER = new ThreadLocal<>();

    /**
     * 设置监控上下文
     */
    public static void setContext(MonitorContext context) {
        CONTEXT_HOLDER.set(context);
        if (context != null && context.getTraceId() != null) {
            org.slf4j.MDC.put("traceId", context.getTraceId());
        }
    }

    /**
     * 获取当前监控上下文
     */
    public static MonitorContext getContext() {
        return CONTEXT_HOLDER.get();
    }

    /**
     * 清除监控上下文
     */
    public static void clearContext() {
        CONTEXT_HOLDER.remove();
        org.slf4j.MDC.remove("traceId");
    }
}
