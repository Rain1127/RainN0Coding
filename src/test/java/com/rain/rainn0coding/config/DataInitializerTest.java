package com.rain.rainn0coding.config;

import com.mybatisflex.core.query.QueryWrapper;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.service.UserService;
import org.junit.jupiter.api.Test;
import org.springframework.dao.RecoverableDataAccessException;
import org.springframework.test.util.ReflectionTestUtils;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DataInitializerTest {

    @Test
    void initAdminUserSkipsWhenDatabaseIsUnavailable() {
        DataInitializer dataInitializer = new DataInitializer();
        UserService userService = mock(UserService.class);
        ReflectionTestUtils.setField(dataInitializer, "userService", userService);

        when(userService.getOne(any(QueryWrapper.class)))
                .thenThrow(new RecoverableDataAccessException("db unavailable"));

        dataInitializer.initAdminUser();

        verify(userService, never()).save(any(User.class));
    }
}
