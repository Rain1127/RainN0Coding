package com.rain.rainn0coding.core;

import com.rain.rainn0coding.constant.AppConstant;
import com.rain.rainn0coding.core.builder.VueProjectBuilder;
import com.rain.rainn0coding.core.python.PythonAiClient;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.model.enums.CodeGenTypeEnum;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AiCodeGeneratorFacadeTest {

    @Test
    void generateAndSaveCodeStreamPersistsCodeFileEvents() throws Exception {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        Path outputDir = Path.of(AppConstant.CODE_OUTPUT_ROOT_DIR, "html_101");
        deleteDirectory(outputDir);
        String sseCodeFile = "data: {\"type\":\"code_file\",\"path\":\"index.html\",\"content\":\"<h1>Hello</h1>\"}";
        when(pythonAiClient.streamCodeGen("1", "101", "generate login page", "html", "user", null, null, null))
                .thenReturn(Flux.just(sseCodeFile, "data: {\"type\":\"done\"}"));

        List<String> result = facade.generateAndSaveCodeStream(
                        "generate login page",
                        CodeGenTypeEnum.HTML,
                        101L,
                        1L,
                        "user"
                )
                .collectList()
                .block();

        assertThat(result).containsExactly(sseCodeFile, "data: {\"type\":\"done\"}");
        assertThat(Files.readString(outputDir.resolve("index.html"))).isEqualTo("<h1>Hello</h1>");
        verifyNoInteractions(vueProjectBuilder);
    }

    @Test
    void generateVueProjectCodeStreamBuildsProjectAfterStreamCompletes() {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        when(pythonAiClient.streamCodeGen("2", "202", "task dashboard", "vue_project", "user", null, null, null))
                .thenReturn(Flux.just("data: {\"type\":\"done\"}"));
        when(vueProjectBuilder.buildProject(AppConstant.CODE_OUTPUT_ROOT_DIR + "/vue_project_202")).thenReturn(true);

        List<String> result = facade.generateAndSaveCodeStream(
                        "task dashboard",
                        CodeGenTypeEnum.VUE_PROJECT,
                        202L,
                        2L,
                        "user"
                )
                .collectList()
                .block();

        assertThat(result).containsExactly("data: {\"type\":\"done\"}");
        verify(vueProjectBuilder).buildProject(AppConstant.CODE_OUTPUT_ROOT_DIR + "/vue_project_202");
    }

    @Test
    void generateVueProjectCodeStreamSkipsSaveAndBuildWhenDoneStatusIsNotSuccess() throws Exception {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        Path outputDir = Path.of(AppConstant.CODE_OUTPUT_ROOT_DIR, "vue_project_205");
        deleteDirectory(outputDir);
        String fileEvent = "data: {\"type\":\"code_file\",\"path\":\"package.json\",\"content\":\"{}\"}";
        String doneEvent = "data: {\"type\":\"done\",\"status\":\"error\"}";
        when(pythonAiClient.streamCodeGen("2", "205", "task dashboard", "vue_project", "user", null, null, null))
                .thenReturn(Flux.just(fileEvent, doneEvent));

        List<String> result = facade.generateAndSaveCodeStream(
                        "task dashboard",
                        CodeGenTypeEnum.VUE_PROJECT,
                        205L,
                        2L,
                        "user"
                )
                .collectList()
                .block();

        assertThat(result).containsExactly(fileEvent, doneEvent);
        assertThat(Files.exists(outputDir.resolve("package.json"))).isFalse();
        verifyNoInteractions(vueProjectBuilder);
    }

    @Test
    void generateVueProjectCodeStreamPropagatesBuildFalse() {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        when(pythonAiClient.streamCodeGen("2", "203", "task dashboard", "vue_project", "user", null, null, null))
                .thenReturn(Flux.just("data: {\"type\":\"done\"}"));
        when(vueProjectBuilder.buildProject(AppConstant.CODE_OUTPUT_ROOT_DIR + "/vue_project_203")).thenReturn(false);

        BusinessException exception = assertThrows(BusinessException.class,
                () -> facade.generateAndSaveCodeStream(
                                "task dashboard",
                                CodeGenTypeEnum.VUE_PROJECT,
                                203L,
                                2L,
                                "user"
                        )
                        .collectList()
                        .block());

        assertThat(exception.getMessage()).contains("build failed");
    }

    @Test
    void generateVueProjectCodeStreamPropagatesBuildException() {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        when(pythonAiClient.streamCodeGen("2", "204", "task dashboard", "vue_project", "user", null, null, null))
                .thenReturn(Flux.just("data: {\"type\":\"done\"}"));
        when(vueProjectBuilder.buildProject(AppConstant.CODE_OUTPUT_ROOT_DIR + "/vue_project_204"))
                .thenThrow(new RuntimeException("npm failed"));

        RuntimeException exception = assertThrows(RuntimeException.class,
                () -> facade.generateAndSaveCodeStream(
                                "task dashboard",
                                CodeGenTypeEnum.VUE_PROJECT,
                                204L,
                                2L,
                                "user"
                        )
                        .collectList()
                        .block());

        assertThat(exception.getMessage()).contains("npm failed");
    }

    @Test
    void generateAndSaveCodeStreamRejectsPathTraversalCodeFile() throws Exception {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        Path outputDir = Path.of(AppConstant.CODE_OUTPUT_ROOT_DIR, "html_404");
        Path escapedFile = Path.of(AppConstant.CODE_OUTPUT_ROOT_DIR, "escape.txt");
        deleteDirectory(outputDir);
        Files.deleteIfExists(escapedFile);
        String traversalEvent = "data: {\"type\":\"code_file\",\"path\":\"../escape.txt\",\"content\":\"owned\"}";
        when(pythonAiClient.streamCodeGen("4", "404", "generate page", "html", "user", null, null, null))
                .thenReturn(Flux.just(traversalEvent, "data: {\"type\":\"done\"}"));

        try {
            BusinessException exception = assertThrows(BusinessException.class,
                    () -> facade.generateAndSaveCodeStream(
                                    "generate page",
                                    CodeGenTypeEnum.HTML,
                                    404L,
                                    4L,
                                    "user"
                            )
                            .collectList()
                            .block());
            assertThat(exception.getMessage()).contains("Invalid generated file path");
            assertThat(Files.exists(escapedFile)).isFalse();
        } finally {
            deleteDirectory(outputDir);
            Files.deleteIfExists(escapedFile);
        }
    }

    @Test
    void generateAndSaveCodeStreamPassesRequestMetadataToPythonClient() {
        AiCodeGeneratorFacade facade = new AiCodeGeneratorFacade();
        PythonAiClient pythonAiClient = mock(PythonAiClient.class);
        VueProjectBuilder vueProjectBuilder = mock(VueProjectBuilder.class);
        ReflectionTestUtils.setField(facade, "pythonAiClient", pythonAiClient);
        ReflectionTestUtils.setField(facade, "vueProjectBuilder", vueProjectBuilder);

        when(pythonAiClient.streamCodeGen("3", "303", "landing page", "html", "admin",
                null, "req-123", "idem-456"))
                .thenReturn(Flux.just("data: {\"type\":\"done\"}"));

        List<String> result = facade.generateAndSaveCodeStream(
                        "landing page",
                        CodeGenTypeEnum.HTML,
                        303L,
                        3L,
                        "admin",
                        "req-123",
                        "idem-456"
                )
                .collectList()
                .block();

        assertThat(result).containsExactly("data: {\"type\":\"done\"}");
        verify(pythonAiClient).streamCodeGen("3", "303", "landing page", "html", "admin",
                null, "req-123", "idem-456");
        verifyNoInteractions(vueProjectBuilder);
    }

    private static void deleteDirectory(Path path) throws IOException {
        if (!Files.exists(path)) {
            return;
        }
        try (Stream<Path> stream = Files.walk(path)) {
            stream.sorted(Comparator.reverseOrder()).forEach(current -> {
                try {
                    Files.deleteIfExists(current);
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
            });
        }
    }
}
