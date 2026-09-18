package com.rain.rainn0coding.queue;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.*;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.util.backoff.FixedBackOff;
import java.util.HashMap;
import java.util.Map;

@Configuration
@EnableKafka
@EnableScheduling
@ConditionalOnProperty(name="app.generation-queue.enabled",havingValue="true")
public class GenerationKafkaConfiguration {
    @Bean
    public KafkaTemplate<String,String> generationKafkaTemplate(GenerationQueueProperties config) {
        Map<String,Object> p=new HashMap<>();
        p.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,config.getBootstrapServers());
        p.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,StringSerializer.class);
        p.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,StringSerializer.class);
        p.put(ProducerConfig.ACKS_CONFIG,"all");
        p.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,true);
        p.put(ProducerConfig.MAX_BLOCK_MS_CONFIG,5000);
        p.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG,5000);
        p.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG,10000);
        return new KafkaTemplate<>(new DefaultKafkaProducerFactory<>(p));
    }
    @Bean
    public ConcurrentKafkaListenerContainerFactory<String,String> generationKafkaListenerFactory(GenerationQueueProperties config) {
        Map<String,Object> p=new HashMap<>();
        p.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,config.getBootstrapServers());
        p.put(ConsumerConfig.GROUP_ID_CONFIG,config.getGroupId());
        p.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,StringDeserializer.class);
        p.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,StringDeserializer.class);
        p.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,false);
        p.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,"earliest");
        p.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG,1);
        p.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG,(config.getTaskTimeoutMinutes()+15)*60*1000);
        var f=new ConcurrentKafkaListenerContainerFactory<String,String>();
        f.setConsumerFactory(new DefaultKafkaConsumerFactory<>(p));
        f.setConcurrency(1);
        f.setAutoStartup(false);
        f.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
        f.getContainerProperties().setShutdownTimeout(60_000);
        // Do not discard a task when storage or Python is temporarily unavailable.
        f.setCommonErrorHandler(new DefaultErrorHandler(new FixedBackOff(5000,FixedBackOff.UNLIMITED_ATTEMPTS)));
        return f;
    }
}
