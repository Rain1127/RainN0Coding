package com.rain.rainn0coding;


import org.mybatis.spring.annotation.MapperScan;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@EnableCaching
@SpringBootApplication
@MapperScan("com.rain.rainn0coding.mapper")
public class RainN0CodingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RainN0CodingApplication.class, args);
    }

}
