# Code Health Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate screenshot-driver concurrency/resource leaks, make Java tests hermetic, and reduce the frontend entry bundle below 500 kB without changing public APIs.

**Architecture:** Preserve the existing static screenshot API but move WebDriver ownership into each invocation through a package-visible factory seam. Isolate external Redis in the Spring context smoke test with a test bean override. Replace global Ant Design Vue registration with compile-time on-demand component resolution using dependencies already present in the frontend.

**Tech Stack:** Java 23, Spring Boot 3.5.9, JUnit 5, Mockito, Selenium, Vue 3, Vite 6, Vitest, `unplugin-vue-components`, Ant Design Vue 4.

---

## File Map

- Modify `src/test/java/com/rain/rainn0coding/utils/WebScreenshotUtilsTest.java`: deterministic driver lifecycle and interrupt regression tests.
- Modify `src/main/java/com/rain/rainn0coding/utils/WebScreenshotUtils.java`: per-call driver ownership, cleanup, and interrupt restoration.
- Modify `src/test/java/com/rain/rainn0coding/RainN0CodingApplicationTests.java`: replace live Redisson with a test override.
- Modify `pom.xml`: add H2 with test scope for MyBatis dialect detection in the full-context smoke test.
- Modify `RainN0Coding-frontend/src/main.ts`: remove global Ant Design Vue plugin registration.
- Modify `RainN0Coding-frontend/vite.config.ts`: enable on-demand Ant Design Vue component resolution.
- Verify `src/main/resources/static/index.html`: generated frontend entry references after the final production build; include only if the repository intentionally tracks the generated entry file.

### Task 1: Screenshot driver lifecycle

**Files:**
- Modify: `src/test/java/com/rain/rainn0coding/utils/WebScreenshotUtilsTest.java`
- Modify: `src/main/java/com/rain/rainn0coding/utils/WebScreenshotUtils.java`

- [ ] **Step 1: Replace the live browser test with failing lifecycle tests**

Use a package-visible `Supplier<WebDriver>` seam in the desired API:

```java
@Test
void blankUrlDoesNotCreateDriver() {
    AtomicBoolean created = new AtomicBoolean();

    String result = WebScreenshotUtils.saveWebPageScreenshot(" ", () -> {
        created.set(true);
        return mock(WebDriver.class);
    });

    assertNull(result);
    assertFalse(created.get());
}

@Test
void closesDriverWhenCaptureFails() {
    WebDriver driver = mock(WebDriver.class);
    doThrow(new RuntimeException("navigation failed"))
            .when(driver).get("https://example.test");

    String result = WebScreenshotUtils.saveWebPageScreenshot(
            "https://example.test", () -> driver);

    assertNull(result);
    verify(driver).quit();
}

@Test
void restoresInterruptFlagWhenPageWaitIsInterrupted() {
    WebDriver driver = mock(
            WebDriver.class,
            withSettings().extraInterfaces(JavascriptExecutor.class));
    when(((JavascriptExecutor) driver).executeScript("return document.readyState"))
            .thenReturn("complete");
    Thread.currentThread().interrupt();
    try {
        assertThrows(
                BusinessException.class,
                () -> WebScreenshotUtils.waitForPageLoad(driver));
        assertTrue(Thread.currentThread().isInterrupted());
    } finally {
        Thread.interrupted();
    }
}
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:JAVA_HOME='D:\Program Files\Java\jdk-23'
mvn -q -Dtest=WebScreenshotUtilsTest test
```

Expected: compilation failure because the `saveWebPageScreenshot(String, Supplier<WebDriver>)` overload does not exist; after introducing only that seam, the interrupt assertion must still fail until the flag is restored.

- [ ] **Step 3: Implement per-invocation ownership and cleanup**

Remove the static driver and ineffective `@PreDestroy` method. Keep the public API and delegate to the factory seam:

```java
public static String saveWebPageScreenshot(String webUrl) {
    return saveWebPageScreenshot(
            webUrl,
            () -> initChromeDriver(DEFAULT_WIDTH, DEFAULT_HEIGHT));
}

static String saveWebPageScreenshot(
        String webUrl,
        Supplier<WebDriver> driverFactory) {
    if (StrUtil.isBlank(webUrl)) {
        log.error("网页 URL 不能为空");
        return null;
    }
    WebDriver driver = null;
    try {
        driver = driverFactory.get();
        String rootPath = System.getProperty("user.dir")
                + "/tmp/screenshot"
                + UUID.randomUUID().toString().substring(0, 8);
        FileUtil.mkdir(rootPath);
        String imageSavePath = rootPath + File.separator
                + RandomUtil.randomNumbers(5) + ".png";
        driver.get(webUrl);
        waitForPageLoad(driver);
        byte[] screenshotBytes = ((TakesScreenshot) driver)
                .getScreenshotAs(OutputType.BYTES);
        saveImage(screenshotBytes, imageSavePath);
        String compressedImageSavePath = rootPath + File.separator
                + RandomUtil.randomNumbers(5) + "_compressed.jpg";
        compressImage(imageSavePath, compressedImageSavePath);
        FileUtil.del(imageSavePath);
        return compressedImageSavePath;
    } catch (Exception e) {
        log.error("保存网页截图失败", e);
        return null;
    } finally {
        closeWebDriver(driver);
    }
}

private static void closeWebDriver(WebDriver driver) {
    if (driver == null) {
        return;
    }
    try {
        driver.quit();
    } catch (Exception e) {
        log.warn("关闭 Chrome WebDriver 失败", e);
    }
}
```

In `waitForPageLoad`, restore the flag before throwing:

```java
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    log.error("等待页面加载被中断", e);
    throw new BusinessException(ErrorCode.SYSTEM_ERROR, "等待页面加载被中断");
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same Maven command. Expected: all `WebScreenshotUtilsTest` tests pass without Redis, Chrome, or internet access.

- [ ] **Step 5: Commit the focused repair**

```powershell
git add -- src/main/java/com/rain/rainn0coding/utils/WebScreenshotUtils.java src/test/java/com/rain/rainn0coding/utils/WebScreenshotUtilsTest.java
git commit -m "fix: isolate screenshot driver lifecycle"
```

### Task 2: Hermetic Spring context smoke test

**Files:**
- Modify: `pom.xml`
- Modify: `src/test/java/com/rain/rainn0coding/RainN0CodingApplicationTests.java`

- [ ] **Step 1: Preserve the existing RED evidence**

Run:

```powershell
$env:JAVA_HOME='D:\Program Files\Java\jdk-23'
mvn -q -Dtest=RainN0CodingApplicationTests test
```

Expected: context load error caused by `RedissonClient` connecting to `localhost:6379`.

- [ ] **Step 2: Override Redis and provide an embedded test datasource**

Add Spring test bean overrides for the external clients:

```java
import org.redisson.api.RedissonClient;
import com.qcloud.cos.COSClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
private RedissonClient redissonClient;

@MockitoBean
private COSClient cosClient;
```

Add `com.h2database:h2` with `<scope>test</scope>` and set the test properties to an H2 in-memory URL with `MODE=MySQL`. Also set `spring.session.store-type=none` so the smoke test does not create a Redis-backed HTTP session store. The test remains `@SpringBootTest`; production configuration is untouched.

- [ ] **Step 3: Run the context test and verify GREEN**

Run the same Maven command. Expected: one test passes without a live Redis server.

- [ ] **Step 4: Run all Java tests**

```powershell
mvn -q test
```

Expected: zero failures and zero errors.

- [ ] **Step 5: Commit the test isolation**

```powershell
git add -- pom.xml src/test/java/com/rain/rainn0coding/RainN0CodingApplicationTests.java docs/superpowers/specs/2026-08-07-code-health-repair-design.md docs/superpowers/plans/2026-08-07-code-health-repairs.md
git commit -m "test: isolate application context dependencies"
```

### Task 3: Ant Design Vue on-demand loading

**Files:**
- Modify: `RainN0Coding-frontend/src/main.ts`
- Modify: `RainN0Coding-frontend/vite.config.ts`
- Potential generated update: `src/main/resources/static/index.html`

- [ ] **Step 1: Record the failing bundle budget**

Build, locate the entry script referenced by `src/main/resources/static/index.html`, and assert its byte size is at most 512000:

```powershell
npm run build
$html = Get-Content -Raw '..\src\main\resources\static\index.html'
$entry = [regex]::Match($html, 'src="/api/(?<path>assets/[^"]+\.js)"').Groups['path'].Value
$entryPath = Join-Path '..\src\main\resources\static' $entry
if ((Get-Item $entryPath).Length -gt 512000) { throw "entry bundle exceeds 500 KiB: $((Get-Item $entryPath).Length) bytes" }
```

Expected: the assertion fails against the current approximately 1.58 MB entry chunk.

- [ ] **Step 2: Enable compile-time component resolution**

Update Vite configuration:

```ts
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'

plugins: [
  vue(),
  tailwindcss(),
  Components({
    dts: false,
    resolvers: [AntDesignVueResolver({ importStyle: 'css-in-js' })],
  }),
],
```

Remove these global registration lines from `src/main.ts`:

```ts
import Antd from 'ant-design-vue'
app.use(Antd)
```

Keep `import 'ant-design-vue/dist/reset.css'` and explicit static API imports such as `message`.

- [ ] **Step 3: Run frontend tests and type checking**

```powershell
npm test
npm run typecheck
```

Expected: 33 test files / 266 tests pass and type checking exits 0.

- [ ] **Step 4: Build and verify GREEN bundle budget**

Run the build and byte-size assertion from Step 1. Expected: build exits 0 and the entry file is below 512000 bytes without changing `chunkSizeWarningLimit`.

- [ ] **Step 5: Review generated output scope and commit**

Inspect `git status --short` and `git ls-files src/main/resources/static`. Stage only source/config changes plus an intentionally tracked generated `index.html` update if required:

```powershell
git add -- RainN0Coding-frontend/src/main.ts RainN0Coding-frontend/vite.config.ts
git add -- src/main/resources/static/index.html
git commit -m "perf: load Ant Design Vue components on demand"
```

Do not stage unrelated untracked static assets.

### Task 4: Final cross-stack verification and review

**Files:**
- Update: `task_plan.md`
- Update: `findings.md`
- Update: `progress.md`

- [ ] **Step 1: Run fresh Java verification**

```powershell
$env:JAVA_HOME='D:\Program Files\Java\jdk-23'
mvn -q test
```

Expected: zero failures/errors.

- [ ] **Step 2: Run fresh Python verification**

```powershell
Set-Location python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests -q --disable-warnings
Set-Location ..
```

Expected: `172 passed, 7 skipped` or a clearly explained updated count with zero failures.

- [ ] **Step 3: Run fresh frontend verification**

```powershell
Set-Location RainN0Coding-frontend
npm test
npm run build
Set-Location ..
```

Expected: all tests pass and the production build exits 0.

- [ ] **Step 4: Perform five-axis review and diff hygiene**

Check correctness, readability, architecture, security, and performance. Run:

```powershell
git diff --check
git status --short
git diff --stat HEAD~3..HEAD
```

Confirm no unrelated user files were staged or committed and generated files are intentional.

- [ ] **Step 5: Update audit records and report residual risks**

Mark phases 6-8 complete only after fresh verification. Record any environment-dependent limitations and the exact final bundle size.
