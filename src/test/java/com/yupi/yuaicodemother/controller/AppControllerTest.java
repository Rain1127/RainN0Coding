package com.yupi.yuaicodemother.controller;

import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.yupi.yuaicodemother.common.BaseResponse;
import com.yupi.yuaicodemother.model.dto.app.AppQueryRequest;
import com.yupi.yuaicodemother.model.entity.App;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.model.vo.AppVO;
import com.yupi.yuaicodemother.service.AppService;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AppControllerTest {

    @Test
    void listMyAppVOByPageShouldClampPageSizeToUserLimit() {
        AppController appController = new AppController();
        AppService appService = mock(AppService.class);
        UserService userService = mock(UserService.class);
        HttpServletRequest request = mock(HttpServletRequest.class);
        ReflectionTestUtils.setField(appController, "appService", appService);
        ReflectionTestUtils.setField(appController, "userService", userService);

        User loginUser = new User();
        loginUser.setId(1L);
        when(userService.getLoginUser(request)).thenReturn(loginUser);
        when(appService.getQueryWrapper(any(AppQueryRequest.class))).thenReturn(QueryWrapper.create());

        Page<App> appPage = new Page<>(1, 20, 0);
        appPage.setRecords(List.of());
        when(appService.page(any(Page.class), any(QueryWrapper.class))).thenReturn(appPage);
        when(appService.getAppVOList(anyList())).thenReturn(List.of());

        AppQueryRequest appQueryRequest = new AppQueryRequest();
        appQueryRequest.setPageNum(1);
        appQueryRequest.setPageSize(100);

        BaseResponse<Page<AppVO>> response = appController.listMyAppVOByPage(appQueryRequest, request);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Page<App>> pageCaptor = ArgumentCaptor.forClass(Page.class);
        verify(appService).page(pageCaptor.capture(), any(QueryWrapper.class));
        assertEquals(20L, pageCaptor.getValue().getPageSize());
        assertEquals(20L, response.getData().getPageSize());
        assertEquals(loginUser.getId(), appQueryRequest.getUserId());
        assertEquals(0, response.getCode());
    }
}
