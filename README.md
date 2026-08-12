# Pali Personhood Lab

首发标签 `v0.1.0` 是可运行的研究预览，不是“已核验模型”稳定版；当前审计快照仍含待人工复核主张。

独立的“巴利人格—条件过程”研究与实验室项目。它把人格处理为随门、所缘、识、触、受、想、行和训练条件而变化的过程，不提供人格诊断、道德评级、动物读心或证悟认证。

## 运行

```powershell
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location)
uvicorn api:app --reload --port 8099
```

另开终端：

```powershell
cd frontend
python -m http.server 4173
```

打开 `http://localhost:4173/`。如果后端地址不同，使用 `/?api=http://host:port`。

## 仓库边界

- `frontend/` 是不依赖原主站 hash 路由和全局变量的静态实验室。
- `backend/` 是无持久化的 FastAPI 服务、Python 确定性镜像和检索适配代码。
- `shared/` 是前后端共用的 schema、fixtures 和 EvidenceLink 资料。
- `research/` 保存主张 registry、审计快照、研究协议和来源锁；原始三藏、全文索引和模型权重不进 Git。
- `artifacts.lock.json` 记录外部数据的版本、哈希、许可证和可重建方式。

## 模型和证据门槛

`pali-canonical/v1` 只使用经律核心条件关系；`theravada-synthesis/v1` 的阿毗达磨、注释和心路解释必须明确标为后期系统化。只有 `three-source-confirmed + human-approved` 的主张可驱动正式模型；当前审计快照仍可能包含 `candidate` 和 `review_required`，不能宣称无遗漏。

## 与原仓库同步

本仓库是人格项目的唯一事实来源。使用 `scripts/publish_integrations.py` 将已验证的前端实验室和后端薄集成层发布到：

- `Bayson-create/Sutta-Study-Guide`
- `Bayson-create/sutta-study-guide-backend`

原仓库的完整站点、账户、论坛、翻译和无关历史不复制到此仓库。
