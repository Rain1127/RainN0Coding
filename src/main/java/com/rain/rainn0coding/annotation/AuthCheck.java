package com.rain.rainn0coding.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;


/**
 * 权限校验
 *
 * @author <a>Rain</a>
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuthCheck {
    /**
     * 必须有某个角色才能访问
     *
     * @return 角色字符串
     */
    String mustRole() default "";
}
