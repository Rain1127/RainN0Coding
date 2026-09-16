package com.rain.rainn0coding.queue;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import reactor.core.publisher.Flux;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Controlled workflow load: no paid model calls, Kafka protocol tested separately. */
class GenerationQueueBurstTest {
    @Test void fiveAcceptedJobsDrainThroughOneSlotAndDuplicateDeliveryIsHarmless() throws Exception {
        var ds=new DriverManagerDataSource("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1","sa","");
        new ResourceDatabasePopulator(new ClassPathResource("sql/generation-queue.sql")).execute(ds);
        var properties=new GenerationQueueProperties();
        var store=new GenerationTaskStore(new JdbcTemplate(ds),new DataSourceTransactionManager(ds),properties);
        var work=mock(GenerationWork.class);
        var active=new AtomicInteger();var peak=new AtomicInteger();var calls=new AtomicInteger();
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        when(work.stream(any())).thenAnswer(invocation->Flux.defer(()->{
            calls.incrementAndGet();peak.accumulateAndGet(active.incrementAndGet(),Math::max);
            entered.countDown();
            try {assertTrue(release.await(5,TimeUnit.SECONDS));} catch(InterruptedException e){throw new RuntimeException(e);}
            active.decrementAndGet();
            return Flux.just("{\"type\":\"progress\",\"phase\":\"coder\"}","{\"type\":\"done\",\"status\":\"success\"}");
        }));
        var executor=new GenerationTaskExecutor(store,work,properties);
        List<String> ids=new ArrayList<>();
        for(int i=1;i<=5;i++)ids.add(store.submit(i,7,"page","html","id-"+i,"trace",()->{}).taskId());
        assertEquals(5,store.count("QUEUED"));
        try(var consumer=Executors.newSingleThreadExecutor()) {
            Future<?> done=consumer.submit(()->{for(String id:ids){executor.execute(id);executor.execute(id);}});
            assertTrue(entered.await(5,TimeUnit.SECONDS));
            assertEquals(1,store.count("RUNNING"));assertEquals(4,store.count("QUEUED"));
            // Reading/replaying progress has no ownership over the worker.
            assertFalse(store.events(ids.getFirst(),0).isEmpty());
            assertFalse(store.events(ids.getFirst(),0).isEmpty());
            release.countDown();done.get(10,TimeUnit.SECONDS);
        } finally {release.countDown();}
        assertEquals(1,peak.get());assertEquals(5,calls.get());
        assertEquals(5,store.count("SUCCEEDED"));assertEquals(0,store.count("QUEUED"));
        verify(work,times(5)).completeHistory(any(),eq("SUCCEEDED"),isNull());
    }
}
