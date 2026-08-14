from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


EXCLUDED_NAMES = {
    ".git",
    ".idea",
    ".venv",
    ".env",
    "__pycache__",
    "local.db",
    "node_modules",
    "runtime",
}
EXCLUDED_SUFFIXES = {".log", ".pyc"}


def _ignored(_directory: str, names: Iterable[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED_NAMES or Path(name).suffix.lower() in EXCLUDED_SUFFIXES
    }


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, ignore=_ignored)


def _copy_file(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def assemble_release(root: Path, destination: Path) -> Path:
    root = root.resolve()
    destination = destination.resolve()
    if destination == root:
        raise ValueError("发行目录不能覆盖项目根目录")
    if destination.exists():
        raise FileExistsError(f"发行目录已存在：{destination}")

    destination.mkdir(parents=True)

    for relative in (
        "backend/app",
        "backend/tests",
        "frontend/dist",
        "frontend/src",
        "mock",
        "examples",
        "mysql",
    ):
        _copy_tree(root / relative, destination / relative)

    for relative in (
        "backend/requirements.txt",
        "backend/data/current_layout.json",
        "backend/data/current_layout_id.txt",
        "frontend/index.html",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/tsconfig.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.node.json",
        "frontend/vite.config.ts",
        "README.md",
        "使用手册.md",
        ".gitignore",
    ):
        _copy_file(root / relative, destination / relative)

    _copy_tree(
        root / "backend/data/layout_templates",
        destination / "backend/data/layout_templates",
    )
    _copy_file(
        root / "output/pdf/霸州晶圆判定工作台操作手册.pdf",
        destination / "操作手册/霸州晶圆判定工作台操作手册.pdf",
    )

    windows = root / "deploy/windows"
    for source in windows.iterdir():
        if source.is_file():
            _copy_file(source, destination / source.name)

    _copy_file(Path(__file__), destination / "deploy/build_release.py")
    _copy_tree(root / "deploy/tests", destination / "deploy/tests")

    inventory = sorted(
        str(path.relative_to(destination)).replace("\\", "/")
        for path in destination.rglob("*")
        if path.is_file()
    )
    (destination / "安装包文件清单.json").write_text(
        json.dumps({"file_count": len(inventory), "files": inventory}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def _write_windows_batch(path: Path, content: str) -> None:
    path.write_text(content.replace("\n", "\r\n"), encoding="utf-8-sig", newline="")


def assemble_offline_release(root: Path, destination: Path) -> Path:
    assemble_release(root, destination)

    venv_python = root / "backend/.venv/Scripts/python.exe"
    if not venv_python.is_file():
        raise FileNotFoundError("缺少 backend/.venv，无法制作离线运行时")

    base_prefix = Path(
        subprocess.check_output(
            [str(venv_python), "-c", "import sys; print(sys.base_prefix)"],
            text=True,
            encoding="utf-8",
        ).strip()
    )
    site_packages = root / "backend/.venv/Lib/site-packages"
    runtime = destination / "runtime"
    python_runtime = runtime / "python"

    shutil.copytree(
        base_prefix,
        python_runtime,
        ignore=lambda directory, names: {
            name
            for name in names
            if name in {"include", "libs", "Scripts", "tcl", "__pycache__"}
            or Path(name).suffix.lower() in {".pyc", ".pdb"}
        },
    )
    shutil.copytree(site_packages, runtime / "site-packages", ignore=_ignored)

    online_installer = destination / "安装并启动.bat"
    if online_installer.exists():
        online_installer.unlink()

    _write_windows_batch(
        destination / "离线安装并启动.bat",
        """@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 晶圆判定系统 - 离线启动
if not exist "runtime\\python\\python.exe" goto missing
if not exist "runtime\\site-packages\\fastapi" goto missing
set "PYTHONPATH=%cd%\\runtime\\site-packages"
set "WAFER_PYTHON=%cd%\\runtime\\python\\python.exe"
call "%cd%\\启动系统.bat"
exit /b %errorlevel%
:missing
echo [ERROR] Offline runtime is incomplete. Extract the complete ZIP and retry.
pause
exit /b 1
""",
    )

    _write_windows_batch(
        destination / "一键启动系统.cmd",
        """@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Wafer Yield System - Start
set "LOG=%cd%\\startup-diagnostic.txt"
>"%LOG%" echo STARTUP_BEGIN
>>"%LOG%" echo DIRECTORY=%cd%
echo ================================================
echo   Wafer Yield System - One Click Start
echo ================================================
echo [1/3] CHECKING_PACKAGE

if not exist "runtime\\python\\python.exe" goto missing_runtime
if not exist "runtime\\site-packages\\fastapi" goto missing_runtime
if not exist "backend\\app\\main.py" goto missing_files
if not exist "frontend\\dist\\index.html" goto missing_files

set "PYTHONPATH=%cd%\\runtime\\site-packages"
set "WAFER_PYTHON=%cd%\\runtime\\python\\python.exe"
echo [2/3] CHECKING_OFFLINE_PYTHON
"%WAFER_PYTHON%" -c "import fastapi, uvicorn; print('RUNTIME_OK')" >>"%LOG%" 2>&1
if errorlevel 1 goto runtime_failed

set "WAFER_NO_PAUSE=1"
echo [3/3] STARTING_SERVER
call "%cd%\\启动系统.bat"
set "START_RESULT=%ERRORLEVEL%"
>>"%LOG%" echo START_RESULT=%START_RESULT%
if not "%START_RESULT%"=="0" goto start_failed

echo.
echo System started. This window can now be closed.
echo Diagnostic log: %LOG%
goto finish

:missing_runtime
>>"%LOG%" echo MISSING_RUNTIME
echo.
echo ERROR: Offline runtime is missing.
echo Extract the COMPLETE ZIP to a normal folder, then run this file again.
goto failed

:missing_files
>>"%LOG%" echo MISSING_SYSTEM_FILES
echo.
echo ERROR: System files are incomplete.
echo Extract the COMPLETE ZIP to a normal folder, then run this file again.
goto failed

:runtime_failed
>>"%LOG%" echo RUNTIME_IMPORT_FAILED
echo.
echo ERROR: Python runtime was blocked or damaged.
echo Check antivirus quarantine, then send startup-diagnostic.txt to support.
goto failed

:start_failed
>>"%LOG%" echo SERVER_START_FAILED
echo.
echo ERROR: Server failed to start.
if exist "runtime\\server.err.log" type "runtime\\server.err.log"
echo Send startup-diagnostic.txt and runtime\\server.err.log to support.
goto failed

:failed
echo Diagnostic log: %LOG%

:finish
echo.
pause
exit /b %START_RESULT%
""",
    )

    instructions = destination / "安装说明.txt"
    original = instructions.read_text(encoding="utf-8-sig")
    original = original.replace(
        "双击“安装并启动.bat”。首次安装需要连接互联网，脚本会安装 Python 3.12 和系统依赖，不需要安装 Node.js。",
        "双击“一键启动系统.cmd”。无需互联网，不需要另装 Python 或 Node.js；窗口会保留，异常时查看 startup-diagnostic.txt。",
    ).replace(
        "本通用安装包",
        "本离线安装包",
    )
    instructions.write_text(original, encoding="utf-8")

    inventory = sorted(
        str(path.relative_to(destination)).replace("\\", "/")
        for path in destination.rglob("*")
        if path.is_file()
    )
    (destination / "安装包文件清单.json").write_text(
        json.dumps({"file_count": len(inventory), "files": inventory}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="组装干净的 Windows 发行目录")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    assembler = assemble_offline_release if args.offline else assemble_release
    assembled = assembler(args.root, args.destination)
    print(assembled)


if __name__ == "__main__":
    main()
