package com.yupi.yuaicodemother.controller;

import com.mybatisflex.core.paginate.Page;
import com.yupi.yuaicodemother.annotation.AuthCheck;
import com.yupi.yuaicodemother.constant.UserConstant;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.beans.factory.annotation.Autowired;
import com.yupi.yuaicodemother.model.entity.AppVersion;
import com.yupi.yuaicodemother.service.AppVersionService;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

/**
 *  控制层。
 *
 * @author <a>Rain</a>
 */
@RestController
@RequestMapping("/appVersion")
public class AppVersionController {

    private static final int MAX_LIST_SIZE = 100;

    @Autowired
    private AppVersionService appVersionService;

    /**
     * 保存。
     *
     * @param appVersion 
     * @return {@code true} 保存成功，{@code false} 保存失败
     */
    @PostMapping("save")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public boolean save(@RequestBody AppVersion appVersion) {
        return appVersionService.save(appVersion);
    }

    /**
     * 根据主键删除。
     *
     * @param id 主键
     * @return {@code true} 删除成功，{@code false} 删除失败
     */
    @DeleteMapping("remove/{id}")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public boolean remove(@PathVariable Long id) {
        return appVersionService.removeById(id);
    }

    /**
     * 根据主键更新。
     *
     * @param appVersion 
     * @return {@code true} 更新成功，{@code false} 更新失败
     */
    @PutMapping("update")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public boolean update(@RequestBody AppVersion appVersion) {
        return appVersionService.updateById(appVersion);
    }

    /**
     * 查询所有。
     *
     * @return 所有数据
     */
    @GetMapping("list")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public List<AppVersion> list() {
        return appVersionService.page(Page.of(1, MAX_LIST_SIZE)).getRecords();
    }

    /**
     * 根据主键获取。
     *
     * @param id 主键
     * @return 详情
     */
    @GetMapping("getInfo/{id}")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public AppVersion getInfo(@PathVariable Long id) {
        return appVersionService.getById(id);
    }

    /**
     * 分页查询。
     *
     * @param page 分页对象
     * @return 分页对象
     */
    @GetMapping("page")
    @AuthCheck(mustRole = UserConstant.ADMIN_ROLE)
    public Page<AppVersion> page(Page<AppVersion> page) {
        ThrowUtils.throwIf(page == null || page.getPageSize() <= 0 || page.getPageSize() > MAX_LIST_SIZE,
                ErrorCode.PARAMS_ERROR, "每页最多查询 100 条版本记录");
        return appVersionService.page(page);
    }

}
