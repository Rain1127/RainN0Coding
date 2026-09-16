package com.rain.rainn0coding.queue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class GenerationTaskStoreTest {
    GenerationTaskStore store;
    GenerationQueueProperties properties;
    @BeforeEach void setup() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(new ClassPathResource("sql/generation-queue.sql")).execute(ds);
        properties = new GenerationQueueProperties();
        store = new GenerationTaskStore(new JdbcTemplate(ds), new DataSourceTransactionManager(ds), properties);
    }
    GenerationTaskStore.Task submit(long app, String key, Runnable history) {
        return store.submit(app, 7L, "make a page", "html", key, "trace", history);
    }
    @Test void duplicateIsDurableAndDoesNotDuplicateHistory() {
        var count = new AtomicInteger();
        var first = submit(1, "same", count::incrementAndGet);
        assertEquals(first.taskId(), submit(1, "same", count::incrementAndGet).taskId());
        assertEquals(1, count.get());
        assertEquals(1, store.pendingDispatches().size());
        assertThrows(RuntimeException.class, () -> store.submit(1,7,"different","html","same","t", () -> {}));
    }
    @Test void historyFailureRollsBackTaskAndOutbox() {
        assertThrows(IllegalStateException.class, () -> submit(1,"x", () -> { throw new IllegalStateException(); }));
        assertNull(store.latest(1,7));
        assertTrue(store.pendingDispatches().isEmpty());
    }
    @Test void capacityIsAtomicAcrossConcurrentSubmissions() throws Exception {
        properties.setMaxPending(2);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(8)) {
            var results = new java.util.ArrayList<Future<Boolean>>();
            for (int i=1;i<=8;i++) {
                long app = i;
                results.add(pool.submit(() -> { start.await(); try { submit(app,"k", () -> {}); return true; } catch (RuntimeException e) {return false;} }));
            }
            start.countDown();
            int accepted=0;
            for (var result:results) if(result.get(10,TimeUnit.SECONDS)) accepted++;
            assertEquals(2,accepted);
        }
    }
    @Test void activeAppAndClaimPreventDuplicateExecution() {
        var task=submit(1,"a",()->{});
        assertThrows(RuntimeException.class,()->submit(1,"b",()->{}));
        assertTrue(store.claim(task.taskId(),"worker"));
        assertFalse(store.claim(task.taskId(),"other"));
        store.append(task.taskId(),"{\"type\":\"progress\"}");
        var count=new AtomicInteger();
        assertTrue(store.finish(task.taskId(),"SUCCEEDED",null,count::incrementAndGet));
        assertFalse(store.finish(task.taskId(),"FAILED","late",count::incrementAndGet));
        assertEquals(1,count.get());
        assertEquals("SUCCEEDED",store.get(task.taskId()).status());
        var events=store.events(task.taskId(),0);
        assertEquals("done",cn.hutool.json.JSONUtil.parseObj(events.getLast().data()).getStr("type"));
        assertEquals(events.size(),events.stream().map(GenerationTaskStore.Event::id).distinct().count());
        assertNotNull(submit(1,"new",()->{}));
    }
    @Test void terminalWriteFailureRemainsRetryableInsteadOfLosingResult() {
        var t=submit(1,"a",()->{}); store.claim(t.taskId(),"w");
        assertThrows(IllegalStateException.class,()->store.finish(t.taskId(),"SUCCEEDED",null,()->{throw new IllegalStateException();}));
        assertEquals("RUNNING",store.get(t.taskId()).status());
        assertFalse(store.events(t.taskId(),0).stream().anyMatch(e->e.data().contains("done")));
    }
    @Test void expiryCannotRaceAndTerminateAnAlreadyClaimedTask() {
        var task=submit(1,"a",()->{});store.claim(task.taskId(),"worker");
        assertFalse(store.finishQueued(task.taskId(),"排队超时",()->{}));
        assertEquals("RUNNING",store.get(task.taskId()).status());
    }
    @Test void maintenanceStopsAdmissionAndClaimsButAllowsExistingIdempotentReads() {
        var first=submit(1,"a",()->{});
        store.setPaused(true);
        assertEquals(first.taskId(),submit(1,"a",()->{}).taskId());
        assertThrows(RuntimeException.class,()->submit(2,"b",()->{}));
        assertFalse(store.claim(first.taskId(),"worker"));
        store.setPaused(false);
        assertTrue(store.claim(first.taskId(),"worker"));
    }
}
