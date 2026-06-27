package com.yupi.yuaicodemother.service.impl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class UserServiceImplTest {

    @Test
    void getEncryptPasswordUsesBcryptHash() {
        UserServiceImpl userService = new UserServiceImpl();

        String encrypted = userService.getEncryptPassword("12345678");

        assertNotEquals("12345678", encrypted);
        assertTrue(encrypted.startsWith("$2"));
    }
}
