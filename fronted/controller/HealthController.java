package com.yupi.yuaicodemother.controller;

import com.yupi.yuaicodemother.common.BaseResponse;
import com.yupi.yuaicodemother.common.ResultUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * @className: HealthController
 * @author: xxy-Rain
 * @date: 2025/12/28 17:27
 * @version: 1.0
 * @description: TODO
 */
@RestController
@RequestMapping("/health")
public class HealthController {

    @GetMapping("/")
    public BaseResponse<String> checkHealth() {
        return ResultUtils.success("Healthy");
    }
}
