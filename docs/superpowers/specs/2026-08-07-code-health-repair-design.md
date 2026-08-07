# Code Health Repair Design

## Goal

Repair the three current, reproducible issues found during the 2026-08-07 audit without broad refactoring or changes to unrelated user-owned files.

## Scope

1. Make webpage screenshot generation safe under concurrent virtual-thread callers and guarantee WebDriver cleanup.
2. Make the default Java test suite independent of a live Redis server and replace the live screenshot smoke test with deterministic regression coverage.
3. Reduce the frontend entry bundle by replacing global Ant Design Vue registration with existing on-demand component tooling.

Out of scope: product feature changes, API contract changes, database migrations, dependency upgrades, deployment changes, and edits to the user's current `pyproject.toml` or unrelated untracked files.

## Design

### Screenshot lifecycle and concurrency

`WebScreenshotUtils` will no longer retain one static `ChromeDriver`. Each `saveWebPageScreenshot` invocation will acquire its own driver through a small factory boundary and close that driver in `finally`, including navigation, screenshot, compression, and unexpected-error paths. The public static API remains unchanged for `ScreenshotServiceImpl`.

A package-visible overload/factory seam will let unit tests provide a fake driver without launching Chrome or accessing the network. Blank URLs must not create a driver. Driver creation failures must preserve the existing `null` failure contract.

### Hermetic Java tests

`WebScreenshotUtilsTest` will stop loading the full Spring context and stop visiting a public website. Regression tests will verify driver creation and cleanup behavior with mocks.

The application context smoke test will override the external `RedissonClient` bean with a test mock. Production Redis configuration remains unchanged; only the test boundary becomes hermetic.

### Frontend bundle optimization

The frontend will use its existing `unplugin-vue-components` dependency with `AntDesignVueResolver`. Global `app.use(Antd)` registration will be removed, while explicit static APIs such as `message` remain normal imports. Route-level lazy loading remains unchanged.

The production build output will be checked against the same 500 kB entry-chunk threshold that currently fails. The purpose is actual entry-bundle reduction, not merely increasing Vite's warning limit.

## Error Handling

- WebDriver cleanup errors will be logged but must not hide the original screenshot failure.
- Interrupted page waits will restore the thread interrupt flag before returning the existing failure result.
- No exception or response contract changes are introduced at the service/controller boundary.

## Test Strategy

1. RED: run the existing Java suite to preserve the Redis-dependent failure evidence.
2. RED: add screenshot lifecycle tests and verify they fail before the factory/cleanup seam exists.
3. GREEN: implement per-invocation drivers and run the focused Java tests.
4. RED: assert the current built frontend entry chunk exceeds 500 kB.
5. GREEN: enable on-demand Ant Design Vue registration, then rerun frontend tests, type-check/build, and the bundle-size assertion.
6. Run Python tests to confirm no cross-service regression.
7. Run the full Java suite, frontend suite/build, and inspect the final Git diff for unrelated changes.

## Completion Criteria

- Concurrent screenshot calls do not share one WebDriver instance.
- Every created WebDriver is closed on success and failure paths.
- Java's default Maven test command no longer requires a running Redis instance.
- Python and frontend test baselines remain green.
- Frontend production entry JavaScript is below 500 kB without raising the warning threshold.
- No unrelated user-owned changes are overwritten.
