package com.rain.rainn0coding.core;

import com.rain.rainn0coding.constant.AppConstant;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/** Version records and compensating filesystem publication share an app-row mutex. */
@Service
public class ArtifactVersionService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final Path output;
    private final Path deploy;
    private static final com.fasterxml.jackson.databind.ObjectMapper JSON = new com.fasterxml.jackson.databind.ObjectMapper();
    @org.springframework.beans.factory.annotation.Value("${app.generation-queue.enabled:false}")
    private boolean queueEnabled;
    public record Version(long id, int number, String description) {}
    public record Move(String current, String previous, String candidate) {}
    public record Journal(long appId, int version, List<Move> moves) {}

    @org.springframework.beans.factory.annotation.Autowired
    public ArtifactVersionService(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this(jdbc, manager, Path.of(AppConstant.CODE_OUTPUT_ROOT_DIR), Path.of(AppConstant.CODE_DEPLOY_ROOT_DIR));
    }
    ArtifactVersionService(JdbcTemplate jdbc, PlatformTransactionManager manager, Path output, Path deploy) {
        this.jdbc=jdbc; this.tx=new TransactionTemplate(manager); this.output=output.toAbsolutePath(); this.deploy=deploy.toAbsolutePath();
    }
    private Map<String,Object> lock(long appId) {
        var rows=jdbc.queryForList("SELECT id,userId,codeGenType,deployKey,currentVersion FROM app WHERE id=? AND isDelete=0 FOR UPDATE",appId);
        if(rows.isEmpty())throw new BusinessException(ErrorCode.NOT_FOUND_ERROR,"应用不存在");
        return rows.getFirst();
    }
    private Path current(Map<String,Object> app) {
        String type=Objects.toString(app.get("codeGenType"));
        if(com.rain.rainn0coding.model.enums.CodeGenTypeEnum.getEnumByValue(type)==null)
            throw new BusinessException(ErrorCode.PARAMS_ERROR,"无效应用类型");
        return output.resolve(type+"_"+app.get("id"));
    }
    private Path store(long app) {return output.resolve(".app-versions").resolve(Long.toString(app));}
    private void owned(Map<String,Object> app,long user) {
        if(((Number)app.get("userId")).longValue()!=user)throw new BusinessException(ErrorCode.NO_AUTH_ERROR);
    }
    public List<Version> list(long appId,long userId) {
        return tx.execute(s->{owned(lock(appId),userId); return jdbc.query(
            "SELECT id,version_number,description FROM app_version WHERE app_id=? ORDER BY version_number DESC LIMIT 100",
            (rs,n)->new Version(rs.getLong(1),rs.getInt(2),rs.getString(3)),appId);});
    }
    public void publish(long appId,Path candidate) {
        publish(appId,candidate,null);
    }
    public void publish(long appId,Path candidate,Map<String,String> expectedBase) {
        tx.executeWithoutResult(s->{
            var app=lock(appId); recover(appId);
            if(expectedBase!=null&&!expectedBase.equals(hashes(current(app))))
                throw new BusinessException(ErrorCode.OPERATION_ERROR,"生成期间当前版本发生变化，候选版本已保留");
            persist(appId,app,candidate,"生成并通过验收");
        });
    }
    private Map<String,String> hashes(Path root) {
        Map<String,String> result=new TreeMap<>();if(!Files.isDirectory(root))return result;
        try {
            Files.walkFileTree(root,new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path p,java.nio.file.attribute.BasicFileAttributes a) {
                    return !p.equals(root)&&Set.of("node_modules",".git",".venv","__pycache__").contains(p.getFileName().toString())?FileVisitResult.SKIP_SUBTREE:FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(Path p,java.nio.file.attribute.BasicFileAttributes a)throws IOException {
                    if(a.isSymbolicLink())throw new IOException("Artifact symlinks are not supported");
                    result.put(root.relativize(p).toString().replace('\\','/'),cn.hutool.crypto.digest.DigestUtil.sha256Hex(p.toFile()));
                    return FileVisitResult.CONTINUE;
                }
            });
        }catch(IOException ex){throw new IllegalStateException(ex);}
        return result;
    }
    public void rollback(long appId,long versionId,long userId) {
        tx.executeWithoutResult(s->{
            if(queueEnabled) {
                jdbc.queryForObject("SELECT id FROM generation_queue_lock WHERE id=1 FOR UPDATE",Integer.class);
                Long active=jdbc.queryForObject("SELECT COUNT(*) FROM generation_task WHERE active_app_id=?",Long.class,appId);
                if(active!=null&&active>0)throw new BusinessException(ErrorCode.CHAT_IN_PROGRESS,"请等待生成任务结束后再回滚");
            }
            var app=lock(appId);owned(app,userId);recover(appId);
            var rows=jdbc.queryForList("SELECT code_content,version_number FROM app_version WHERE id=? AND app_id=?",versionId,appId);
            if(rows.isEmpty())throw new BusinessException(ErrorCode.NOT_FOUND_ERROR,"版本不存在");
            Path snapshot=Path.of(rows.getFirst().get("code_content").toString()).toAbsolutePath().normalize();
            if(!snapshot.startsWith(store(appId))||!Files.isDirectory(snapshot))
                throw new BusinessException(ErrorCode.OPERATION_ERROR,"版本快照不可用");
            try {
                Path candidate=ArtifactPublisher.candidate(current(app));copy(snapshot,candidate);
                persist(appId,app,candidate,"回滚至版本 "+rows.getFirst().get("version_number"));
            }catch(IOException ex){throw new IllegalStateException(ex);}
        });
    }
    private void persist(long appId,Map<String,Object> app,Path candidate,String description) {
        try {
            Files.createDirectories(store(appId));
            Integer max=jdbc.queryForObject("SELECT MAX(version_number) FROM app_version WHERE app_id=?",Integer.class,appId);
            if(max==null&&Files.isDirectory(current(app))) {
                Path legacy=store(appId).resolve("version-0-"+UUID.randomUUID());
                copy(current(app),legacy);
                jdbc.update("INSERT INTO app_version(app_id,version_number,code_content,description,create_time) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                    appId,0,legacy.toString(),"优化前保留版本");
                max=0;
            }
            int version=max==null?1:max+1;
            Path snapshot=store(appId).resolve("version-"+version+"-"+UUID.randomUUID());
            copy(candidate,snapshot);
            List<Move> moves=new ArrayList<>();
            moves.add(move(current(app),candidate));
            String key=Objects.toString(app.get("deployKey"),"");
            if(!key.isBlank() && description.startsWith("回滚")) {
                if(!key.matches("[A-Za-z0-9_-]+"))throw new IOException("Invalid deployment key");
                Path deployCurrent=deploy.resolve(key);
                Path staged=ArtifactPublisher.candidate(deployCurrent);
                Path source=Files.isDirectory(snapshot.resolve("dist"))?snapshot.resolve("dist"):snapshot;
                if(!Files.exists(source.resolve("index.html"))&&Files.exists(source.resolve("src/index.html")))source=source.resolve("src");
                copy(source,staged);moves.add(move(deployCurrent,staged));
            }
            Path journal=store(appId).resolve("pending.json");
            Path temp=store(appId).resolve("pending.tmp");
            Files.writeString(temp,JSON.writeValueAsString(new Journal(appId,version,moves)));
            Files.move(temp,journal,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
                @Override public void afterCompletion(int status) {
                    if(status==STATUS_COMMITTED) {try{Files.deleteIfExists(journal);}catch(IOException ignored){}}
                    else recover(appId);
                }
            });
            jdbc.update("INSERT INTO app_version(app_id,version_number,code_content,description,create_time) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                appId,version,snapshot.toString(),description);
            for(Move move:moves) {
                Path live=Path.of(move.current());
                if(Files.exists(live))Files.move(live,Path.of(move.previous()));
                Files.move(Path.of(move.candidate()),live);
            }
            if(jdbc.update("UPDATE app SET currentVersion=? WHERE id=?",version,appId)!=1)throw new IOException("Version pointer update failed");
        }catch(IOException ex){throw new IllegalStateException("版本发布失败，原版本将恢复",ex);}
    }
    private Move move(Path current,Path candidate) {
        return new Move(current.toString(),current.resolveSibling("."+current.getFileName()+".previous-"+UUID.randomUUID()).toString(),candidate.toString());
    }
    static void copy(Path source,Path destination)throws IOException {
        Files.walkFileTree(source,new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(Path path,java.nio.file.attribute.BasicFileAttributes attrs)throws IOException {
                if(!path.equals(source)&&Set.of("node_modules",".git",".venv","__pycache__").contains(path.getFileName().toString()))return FileVisitResult.SKIP_SUBTREE;
                Files.createDirectories(destination.resolve(source.relativize(path)));return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path path,java.nio.file.attribute.BasicFileAttributes attrs)throws IOException {
                if(attrs.isSymbolicLink())throw new IOException("Artifact symlinks are not supported");
                Path target=destination.resolve(source.relativize(path));
                Files.createDirectories(target.getParent());Files.copy(path,target,StandardCopyOption.REPLACE_EXISTING);return FileVisitResult.CONTINUE;
            }
        });
    }
    public void recover(long appId) {
        Path journal=store(appId).resolve("pending.json");
        if(!Files.isRegularFile(journal))return;
        try {
            Journal saved=JSON.readValue(Files.readString(journal),Journal.class);
            if(saved.appId()!=appId)throw new IOException("Artifact journal app mismatch");
            Integer current=jdbc.queryForObject("SELECT currentVersion FROM app WHERE id=?",Integer.class,appId);
            if(current==null||current!=saved.version())for(Move move:saved.moves()) {
                Path live=Path.of(move.current()),previous=Path.of(move.previous()),candidate=Path.of(move.candidate());
                if(!live.normalize().startsWith(output)&&!live.normalize().startsWith(deploy))throw new IOException("Unsafe recovery path");
                if(Files.exists(previous)) {
                    if(Files.exists(live))Files.move(live,candidate.resolveSibling(candidate.getFileName()+".aborted-"+UUID.randomUUID()));
                    Files.move(previous,live);
                } else if(!Files.exists(candidate)&&Files.exists(live))Files.move(live,candidate);
            }
            Files.deleteIfExists(journal);
        }catch(IOException ex){throw new IllegalStateException("版本恢复失败",ex);}
    }
    @org.springframework.context.event.EventListener(org.springframework.boot.context.event.ApplicationReadyEvent.class)
    public void recoverOnStartup() throws IOException {
        Path root=output.resolve(".app-versions");if(!Files.isDirectory(root))return;
        try(var paths=Files.list(root)){for(Path p:paths.toList())if(p.getFileName().toString().matches("[0-9]+"))recover(Long.parseLong(p.getFileName().toString()));}
    }
}
