# Pali personhood process system: backend research notes

本仓库的 `personhood/` 是静态站点模型的 Python 镜像，供未来 skill 和 CI 使用；它不替代 `search_service/` 的检索职责。

## V4 provenance boundary

后端现有混合检索已经能返回 `work_id / row_id / paranum / anchor / source / version` 契约。人格系统只把这些字段作为引文键：没有从索引命中的真实记录，就不填 locator。`docs/SEARCH_SOURCE_LOCK.md` 记录了 V4 权威 Azure Blob、217 works、22,698 corpus rows、词典行数和版本锁；`graphify-out/graph.json` 可查询 `V4 authority source → SearchIndex → Record → HybridEngine → rrf_merge()` 的真实关系。

## Claim matrix

| 主张 | 主要锚点 | 解释层 | 运行时限制 |
| --- | --- | --- | --- |
| 六门和所缘构成“全部”的认知边界 | SN 35.23 | canonical | 只创建门/所缘/识/触条件 |
| 触缘受、受缘爱 | SN 12.23 | canonical | 未训练分支显示局部循环，不当作固定人格 |
| 触后想、寻思和戏论展开 | MN 18 | canonical | 不宣称固定毫秒顺序 |
| 五蕴非我 | SN 22.59 | canonical | 聚合标签，不生成人格实体 |
| 正念/明觉和起灭观察 | MN 10, DN 22 | canonical | 训练干预只改变当前 episode 条件 |
| citta-vīthi、随眠、速行 | 阿毗达磨/注释传统 | abhidhamma | 只在 synthesis 版本显示并标“后期系统化” |

外部研究使用系统检索日志和版本书目；不会声称穷尽全球学术文献。现代心理学仅用于界面可读性比较，不改写巴利术语或生成临床人格诊断。

## Production path

1. 使用 `/api/search/v1/hybrid` 对三语查询集召回 V4 行，写入 evidence manifest 的真实 locator。
2. 保留 `source/version`，按模型版本生成可回滚 manifest；缓存和降级由现有 hybrid service 负责。
3. 将 `personhood/engine.py` 接入 CI：验证每个事件有 EvidenceLink、每个 contact 有门/所缘/识、交互无内部状态泄漏。
4. 先 shadow，再小流量预览；清空 `SUTTA_HYBRID_SEARCH_BASE` 可回滚到前端静态检索。

## 已接入的运行时与证据审计（2026-08-12）

- `POST /api/personhood/episodes` 使用 Python `run_interaction`，输入同一 `modelVersion + scenario + agents + interventions + seed` 必得同一 JSON；最多 6 轮，只传播外化行动。
- `GET /api/personhood/evidence` 返回 `docs/PERSONHOOD_EVIDENCE_AUDIT.json` 的最近快照；快照由 `scripts/audit_personhood_evidence.py` 基于 `personhood/claim_registry.json` 生成，状态严格分为 `confirmed / candidate / review_required / unavailable`。
- `POST /api/personhood/explain` 先重跑 trace，再把 trace、问题和既有 evidence IDs 交给现有 provider；不写入 Gotama 会话表，provider 失败时返回确定性降级说明。
- V4 locator 当前只能确认 `v4:work_id:row_id`，尚无稳定的 canonical UID 映射；因此有 UID 的 canonical claim 在本次快照中保留 `review_required`。这代表审计未完成，不代表经文不存在。
- 真实网络核验受到当前环境对公开站点的连接/超时限制时，审计会记录 `unavailable`，不会以候选结果冒充 SuttaCentral 或 Early Buddhist 的确认。
