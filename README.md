# 晶圆台良品/不良品判定可视化系统

Vue3 + FastAPI。默认 **Mock 模式**（`mock/eav_rows.json`），可切换连接设备库 `mg_nano.summaryhead` / `summarydetail`。

工程师操作说明见：[使用手册.md](./使用手册.md)

## 启动（推荐）

**双击 `一键启动.bat`**（或上一级目录桌面文件夹里的同名文件）：

- 自动安装 / 修复 `uv`、Python 3.12、后端虚拟环境与依赖  
- 自动检测 Node.js（缺失时尝试 winget 安装 LTS）  
- 自动 `npm install`（如需要）  
- 分别打开后端 `:8000`、前端 `:5173` 窗口，并打开浏览器  

停止：关闭那两个黑色窗口，或双击 `停止服务.bat`。

### 手动启动（可选）

后端：

```bash
cd wafer-yield/backend
# 首次可双击 安装依赖.bat
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

工程师现场请用稳定模式（不要加 `--reload`）。写本地库或杀毒扫盘会触发热重启，几分钟后常出现「拒绝连接」。

前端：

```bash
cd wafer-yield/frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173/

> 若系统自带的 `C:\Program Files\Python312` 标准库损坏，请用一键启动或 `uv` 提供的 Python，不要直接用坏掉的 `python`。

## 功能摘要

- 按 Min/Max 多参数判定（全部通过才为 Pass）
- **上传 Shot 布局 TSV**（FIELD_SPEC：Level1 Shot + Level2 小格模板，样例见 `examples/SF_DR8.txt`），按 Level1 `custom`→`(col,row)` 画图谱；不再使用固定 34 位网格
- 自研 Wafer Map：Pass/Fail 上色，点击 Shot → 选择 Die 看详情
- Die 选择器由 Level2 模板动态生成；矩形内缺失位为 Test Key
- DR8-PIC **默认模板不可覆盖**；可另存客户标准，刷新后保持上次选用模板
- 支持从数据库 `ItemName` 追加自定义判定项
- Excel 导出（汇总 / 全部 / 不良品清单）
- 数据库密码本地加密存储（环境变量 `WAFER_YIELD_SECRET`）

## 设备库查询

库：`mg_nano`  
表：`summaryhead`（头表）+ `summarydetail`（明细）  
关联：`summaryhead.ID = summarydetail.HeadID`

建表脚本：`mysql/init_mg_nano.sql`（对齐工程师 `head.csv` / `detail.csv`）。

| 业务含义 | 字段 | 说明 |
| --- | --- | --- |
| 晶圆编号 | `h.Wafer` | 如 `UMU26A001R-9` |
| Shot | `h.Shot` | 如 `62` |
| SN | `h.SN` | 如 `"(5,6)"$$SN0303` |
| 参数名称 | `d.ItemName` | 如 `OnChipLoss`、`EC-EC` |
| 参数单位 | `d.ItemUnit` | `DB` / `uA` / `nA` |
| 参数实测值 | `d.ItemValue` | 浮点实测 |
| 波长 | `d.WaveLength` | **只处理 `1311`**，忽略 1304/1318 |

### 标准查询（仅 1311）

```sql
SELECT
  h.Wafer, h.Shot, h.SN,
  d.ItemName, d.ItemUnit, d.ItemValue, d.WaveLength, d.Chnl
FROM mg_nano.summaryhead h
JOIN mg_nano.summarydetail d ON h.ID = d.HeadID
WHERE h.Wafer = 'UMU26A001R-9'
  AND TRIM(CAST(d.WaveLength AS CHAR)) IN ('1311', '1311.0');
```

> 若现场库列名已规范为 `ItemUnit` / `ItemValue`，后端会自动回退兼容；对接时以实际 `SHOW COLUMNS` 为准。
