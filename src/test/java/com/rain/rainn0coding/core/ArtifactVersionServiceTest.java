package com.rain.rainn0coding.core;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import java.nio.file.*;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class ArtifactVersionServiceTest {
    Path root;
    JdbcTemplate jdbc;
    ArtifactVersionService service;
    Path output,deploy;
    @BeforeEach void setup()throws Exception {
        Path testRoot=Path.of(System.getProperty("user.dir"),".tmp-optimization-java").toAbsolutePath().normalize();
        Files.createDirectories(testRoot);root=Files.createTempDirectory(testRoot,"version-");
        var ds=new DriverManagerDataSource("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_UPPER=FALSE;DB_CLOSE_DELAY=-1","sa","");
        jdbc=new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE app(id BIGINT PRIMARY KEY,userId BIGINT,codeGenType VARCHAR(64),deployKey VARCHAR(64),currentVersion INT,isDelete INT DEFAULT 0)");
        jdbc.execute("CREATE TABLE app_version(id BIGINT AUTO_INCREMENT PRIMARY KEY,app_id BIGINT,version_number INT,code_content VARCHAR(4096),description VARCHAR(1024),create_time TIMESTAMP)");
        jdbc.update("INSERT INTO app(id,userId,codeGenType) VALUES(1,7,'html')");
        output=root.resolve("output");deploy=root.resolve("deploy");Files.createDirectories(output);Files.createDirectories(deploy);
        service=new ArtifactVersionService(jdbc,new DataSourceTransactionManager(ds),output,deploy);
    }
    Path candidate(String text)throws Exception {
        Path p=Files.createTempDirectory(output,"candidate-");Files.writeString(p.resolve("index.html"),text);return p;
    }
    @Test void publicationRecordsVersionAndRollbackRestoresFilesDatabaseAndDeployment()throws Exception {
        service.publish(1,candidate("one"));
        long first=service.list(1,7).getFirst().id();
        service.publish(1,candidate("two"));
        jdbc.update("UPDATE app SET deployKey='abc' WHERE id=1");
        Files.createDirectories(deploy.resolve("abc"));Files.writeString(deploy.resolve("abc/index.html"),"two");
        service.rollback(1,first,7);
        assertEquals("one",Files.readString(output.resolve("html_1/index.html")));
        assertEquals("one",Files.readString(deploy.resolve("abc/index.html")));
        assertEquals(3,jdbc.queryForObject("SELECT currentVersion FROM app WHERE id=1",Integer.class));
        assertEquals(3,service.list(1,7).size());
    }
    @Test void authorizationPreventsRollback()throws Exception {
        service.publish(1,candidate("one"));
        assertThrows(RuntimeException.class,()->service.rollback(1,service.list(1,7).getFirst().id(),9));
        assertEquals("one",Files.readString(output.resolve("html_1/index.html")));
    }
    @Test void changedBaseCannotBeOverwrittenByOlderCandidate()throws Exception {
        service.publish(1,candidate("one"));
        Path staged=candidate("two");
        assertThrows(RuntimeException.class,()->service.publish(1,staged,java.util.Map.of("index.html","stale-hash")));
        assertEquals("one",Files.readString(output.resolve("html_1/index.html")));
        assertTrue(Files.isDirectory(staged));
    }
    @Test void existingUnversionedOutputGetsARollbackEntry()throws Exception {
        Files.createDirectories(output.resolve("html_1"));Files.writeString(output.resolve("html_1/index.html"),"legacy");
        service.publish(1,candidate("new"));
        var old=service.list(1,7).stream().filter(v->v.number()==0).findFirst().orElseThrow();
        service.rollback(1,old.id(),7);
        assertEquals("legacy",Files.readString(output.resolve("html_1/index.html")));
    }
    @Test void databaseFailureRestoresPreviouslyPublishedFiles()throws Exception {
        service.publish(1,candidate("one"));
        jdbc.execute("ALTER TABLE app ADD CONSTRAINT reject_second CHECK (currentVersion < 2)");
        Path failed=candidate("two");
        assertThrows(RuntimeException.class,()->service.publish(1,failed));
        assertEquals("one",Files.readString(output.resolve("html_1/index.html")));
        assertEquals(1,service.list(1,7).size());
    }
    @Test void startupRecoversFilesystemSwitchWhoseDatabaseTransactionDidNotCommit()throws Exception {
        service.publish(1,candidate("one"));
        Path live=output.resolve("html_1"), staged=candidate("two"), previous=output.resolve(".html_1.previous-crash");
        Path journal=output.resolve(".app-versions/1/pending.json");
        var record=new ArtifactVersionService.Journal(1,2,java.util.List.of(
            new ArtifactVersionService.Move(live.toString(),previous.toString(),staged.toString())));
        Files.writeString(journal,new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(record));
        Files.move(live,previous);Files.move(staged,live);
        service.recoverOnStartup();
        assertEquals("one",Files.readString(live.resolve("index.html")));
        assertEquals(1,jdbc.queryForObject("SELECT currentVersion FROM app WHERE id=1",Integer.class));
        assertFalse(Files.exists(journal));
    }
}
