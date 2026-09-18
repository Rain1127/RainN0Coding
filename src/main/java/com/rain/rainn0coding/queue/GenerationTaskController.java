package com.rain.rainn0coding.queue;

import com.rain.rainn0coding.common.BaseResponse;
import com.rain.rainn0coding.common.ResultUtils;
import com.rain.rainn0coding.ratelimiter.annotation.RateLimit;
import com.rain.rainn0coding.ratelimiter.enums.RateLimitType;
import com.rain.rainn0coding.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/app/generation/tasks")
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationTaskController {
    public record SubmitRequest(Long appId,String message,String idempotencyKey) {}
    private final GenerationQueueService queue;
    private final UserService users;
    public GenerationTaskController(GenerationQueueService queue,UserService users) {this.queue=queue;this.users=users;}
    @PostMapping
    @RateLimit(limitType=RateLimitType.USER,rate=5,rateInterval=60,message="提交过于频繁，请稍后再试")
    public BaseResponse<GenerationQueueService.Snapshot> submit(@RequestBody SubmitRequest body,HttpServletRequest request) {
        return ResultUtils.success(queue.submit(body.appId(),body.message(),body.idempotencyKey(),users.getLoginUser(request)));
    }
    @GetMapping("/latest")
    public BaseResponse<GenerationQueueService.Snapshot> latest(@RequestParam Long appId,HttpServletRequest request) {
        return ResultUtils.success(queue.latest(appId,users.getLoginUser(request)));
    }
    @GetMapping("/{id}")
    public BaseResponse<GenerationQueueService.Snapshot> get(@PathVariable String id,HttpServletRequest request) {
        return ResultUtils.success(queue.get(id,users.getLoginUser(request)));
    }
    @PostMapping("/{id}/pause")
    public BaseResponse<GenerationQueueService.Snapshot> pause(@PathVariable String id,HttpServletRequest request) {
        return ResultUtils.success(queue.pause(id,users.getLoginUser(request)));
    }
    @PostMapping("/{id}/resume")
    @RateLimit(limitType=RateLimitType.USER,rate=10,rateInterval=60,message="继续任务请求过于频繁")
    public BaseResponse<GenerationQueueService.Snapshot> resume(@PathVariable String id,HttpServletRequest request) {
        return ResultUtils.success(queue.resume(id,users.getLoginUser(request)));
    }
    @GetMapping(value="/{id}/events",produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(@PathVariable String id,@RequestParam(defaultValue="0") long after,
            @RequestHeader(value="Last-Event-ID",required=false) Long lastEventId,HttpServletRequest request) {
        return queue.events(id,lastEventId==null?after:lastEventId,users.getLoginUser(request));
    }
}
