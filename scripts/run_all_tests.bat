@echo off
REM Run all TwitchBot tests. Python tests are the blocking step; Node steps
REM (UI Jest, Overlay build) skip with a warning if npm is not available.
REM Exit code is non-zero only when Python tests fail.

setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_ROOT=%SCRIPT_DIR%\.."
pushd "%PROJECT_ROOT%"

echo === Python tests (pytest) ===
python -m pytest -q
if errorlevel 1 (
    echo [run_all_tests] Python tests FAILED.
    popd
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [run_all_tests] npm not found - skipping UI Jest and Overlay build steps.
    popd
    exit /b 0
)

echo === UI Jest tests ===
pushd "src\UI\static"
call npm ci
if errorlevel 1 goto ui_ci_failed
call npm test
if errorlevel 1 goto ui_test_failed
popd

echo === Overlay JS build ===
pushd "src\Overlay_project"
call npm ci
if errorlevel 1 goto ov_ci_failed
call npm run build
if errorlevel 1 goto ov_build_failed
popd

popd
echo [run_all_tests] All tests passed.
exit /b 0

:ui_ci_failed
echo [run_all_tests] npm ci failed in src\UI\static
popd
popd
exit /b 1

:ui_test_failed
echo [run_all_tests] UI Jest tests FAILED.
popd
popd
exit /b 1

:ov_ci_failed
echo [run_all_tests] npm ci failed in src\Overlay_project
popd
popd
exit /b 1

:ov_build_failed
echo [run_all_tests] Overlay build FAILED.
popd
popd
exit /b 1
