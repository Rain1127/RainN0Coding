package com.rain.rainn0coding;

import com.qcloud.cos.COSClient;
import org.junit.jupiter.api.Test;
import org.redisson.api.RedissonClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(properties = {
        "spring.profiles.active=test",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.url=jdbc:h2:mem:rainn0coding-test;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.session.store-type=none"
})
class RainN0CodingApplicationTests {

    @MockitoBean
    private RedissonClient redissonClient;

    @MockitoBean
    private COSClient cosClient;

    @Test
    void contextLoads() {
    }

}
