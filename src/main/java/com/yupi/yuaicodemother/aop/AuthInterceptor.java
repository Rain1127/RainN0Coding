package com.yupi.yuaicodemother.aop;

import cn.dev33.satoken.stp.StpUtil;
import com.yupi.yuaicodemother.annotation.AuthCheck;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

/**
 * 权限校验拦截器 —— 底层基于 Sa-Token。
 */
@Aspect
@Component
public class AuthInterceptor {

    @Around("@annotation(authCheck)")
    public Object doIntercept(ProceedingJoinPoint joinPoint, AuthCheck authCheck) throws Throwable {
        String mustRole = authCheck.mustRole();
        // 不需要权限，直接放行
        if (mustRole == null || mustRole.isEmpty()) {
            return joinPoint.proceed();
        }
        // 使用 Sa-Token 检查登录态
        try {
            StpUtil.checkLogin();
        } catch (Exception e) {
            throw new BusinessException(ErrorCode.NOT_LOGIN_ERROR);
        }
        // 使用 Sa-Token 检查角色
        try {
            StpUtil.checkRole(mustRole);
        } catch (Exception e) {
            throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
        }
        return joinPoint.proceed();
    }
}
