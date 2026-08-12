# 检索构建输入锁定记录

本文件是本轮构建的输入快照说明。它不复制或改写 V4/Azure 发布物；构建器从指定只读目录读取，`bootstrap_search_sources.py` 可在单独的非 Git artifacts 目录中保存 metadata 和 SHA-256。

## V4（Azure 权威源）

- Base：`https://suttastudyguidestor.blob.core.windows.net/tipitaka-public/tipitaka/v1`
- `manifest.json`：已只读核验
- corpus：217 部作品、422,698 行
- dictionaries：26 个表、2,436,672 条
- proper nouns：634 条；user dictionary：1 条
- source ZIP SHA-256：`e7c61c24622383d2c1fd2677a9160a41765d30ecdfb099766e2b50aba6d9e662`
- `catalog/works.json`：217 个条目；完整文件 SHA 在下载后由 source lock 写入

## Early-Buddhist

- Remote：`https://github.com/Bayson-create/Early-Buddhist.git`
- Branch：`main`
- Commit：`c68dd382ef68546a0fda77e4445967de6c4c1058`
- 本地只读源：`D:\WSL\Ubuntu-22.04\Early-Buddhist\docs`
- 当前索引文件计数：英文 206,440 行，中文 149,860 行；按 `(uid, segment)` 去重后的 union 为 354,704 条。中文和英文使用不同定位体系时不会猜测对齐，会按独立 canonical locator 保存。

## 仓库基线

- 前端 `Sutta-Study-Guide`：`689e7e74e9907038318aa915a35cc3a1e7bfbc6d`
- 后端 `sutta-study-guide-backend`：`84a16afc5e948d1cf633162b7694579e3cafadd6`
- 两个已有仓库均存在用户未提交文件；构建输出必须放在非 Git 的版本化 artifacts 目录，禁止覆盖 `tipitaka/v1`、SQLite、翻译和术语历史。

## P0 locator contract (2026-08-11)

The pinned Early-Buddhist source contains 356,300 raw rows: 149,860 Chinese
and 206,440 English.  The earlier 354,704 union was caused by 1,596 Chinese
rows sharing `uid+i` across legacy translators, not by missing source data.
The projection now preserves all rows with these stable namespaces:

- `early:zh:{uid}:{author_uid}:{i}` for Chinese legacy translations;
- `early:en:{uid}:{segment_id}` for English/Pali records.

Cross-language rows are not guessed to be aligned.  The full P0 lexical
projection therefore contains 422,698 V4 records plus 356,300 Early-Buddhist
records = 778,998 unique locators.
