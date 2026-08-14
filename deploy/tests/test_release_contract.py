from __future__ import annotations

import subprocess
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from deploy.build_release import assemble_offline_release, assemble_release


ROOT = Path(__file__).resolve().parents[2]


class WindowsReleaseContractTest(unittest.TestCase):
    def test_assembled_package_is_runnable_and_has_no_site_database(self) -> None:
        required = {
            "安装并启动.bat",
            "启动系统.bat",
            "停止系统.bat",
            "检测连接.bat",
            "开放局域网访问.bat",
            "安装说明.txt",
            "package_manifest.json",
        }
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "release"
            assemble_release(ROOT, destination)

            self.assertTrue(required.issubset({path.name for path in destination.iterdir()}))
            self.assertTrue((destination / "backend" / "app" / "main.py").is_file())
            self.assertTrue((destination / "frontend" / "dist" / "index.html").is_file())
            self.assertTrue((destination / "操作手册" / "霸州晶圆判定工作台操作手册.pdf").is_file())

            forbidden_names = {"local.db", ".venv", "node_modules", ".git", ".idea", "__pycache__"}
            packaged_names = {path.name for path in destination.rglob("*")}
            self.assertTrue(forbidden_names.isdisjoint(packaged_names))
            self.assertFalse(any(path.suffix == ".log" for path in destination.rglob("*")))

            templates = list((destination / "backend" / "data" / "layout_templates").glob("*.json"))
            self.assertGreaterEqual(len(templates), 1)

            for batch in destination.glob("*.bat"):
                raw = batch.read_bytes()
                self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), f"{batch.name} 缺少 UTF-8 BOM")
                self.assertIn(b"\r\n", raw, f"{batch.name} 必须使用 Windows CRLF 换行")

    def test_offline_package_contains_python_and_never_downloads_at_install_time(self) -> None:
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "offline-release"
            assemble_offline_release(ROOT, destination)

            self.assertTrue((destination / "runtime" / "python" / "python.exe").is_file())
            self.assertTrue((destination / "runtime" / "site-packages" / "fastapi").is_dir())
            installer = (destination / "离线安装并启动.bat").read_text(encoding="utf-8-sig")
            self.assertNotIn("uv python install", installer)
            self.assertNotIn("pip install", installer)
            self.assertNotIn("http://", installer)
            self.assertNotIn("https://", installer)

            (destination / "runtime" / "python" / "python.exe").rename(
                destination / "runtime" / "python" / "python.missing"
            )
            launcher = destination / "一键启动系统.cmd"
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "call", str(launcher)],
                cwd=destination,
                input="\n",
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            diagnostic = destination / "startup-diagnostic.txt"
            self.assertTrue(diagnostic.is_file())
            self.assertIn("MISSING_RUNTIME", diagnostic.read_text(encoding="utf-8"))
            self.assertIn("CHECKING_PACKAGE", result.stdout)


if __name__ == "__main__":
    unittest.main()
