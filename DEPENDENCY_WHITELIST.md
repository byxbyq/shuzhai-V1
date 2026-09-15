# 依赖白名单（Dependency Whitelist）

> 书斋 V66 允许引入的第三方依赖，**仅限下表已核准的宽松许可 / 已记录例外依赖**。
> 新增依赖必须：① 许可符合下方「许可政策」；② 在此登记；③ 通过 `tools/gate_license.py` 门禁。

## 许可政策（对应最终拍板三项核心决策）

1. **硬禁止（零容忍，对应决策 1/3）**
   - 非商业许可：`PolyForm Noncommercial`、`CC-BY-NC` 等一切限制商业使用的许可。
   - 强 Copyleft：`AGPL`（任何版本）—— 网络使用即触发源码公开，与「可商用、全商业开放路径保留」根本冲突。
   - 作为**库依赖**引入的 `GPL/LGPL`（会传染书斋自有代码、迫使其开源）。
2. **允许（宽松许可）**：`MIT` / `BSD-2/3-Clause` / `Apache-2.0` / `HPND` / `ISC` / `PSF` / `Python-2.0`，全部商业可用、无传染。
3. **已记录例外（弱 Copyleft，商业可用，已在下表标注 ⚠️）**
   - `MPL-2.0`（certifi、tqdm）：文件级 Copyleft，仅修改该库源文件需回吐，不影响书斋自有代码；商业可用。
   - `GPL-2.0-with-exception`（pyinstaller）：**仅构建/打包期工具**，其特殊例外条款明确允许用它打包并分发闭源/商业程序；非引擎运行时依赖。

> 说明：lengdu（PolyForm Noncommercial）已彻底移除重写，不在本表；InkOS/ProseForge/ebooklib 痕迹已清零，见 `THIRD_PARTY_LICENSES.md`。

## 已核准依赖（requirements-mobile.txt + requirements.txt 并集，共 70 项）

| 包 | 版本 | 许可 | 用途 |
|----|------|------|------|
| annotated-doc | 0.0.4 | BSD-2-Clause | OpenAPI 文档注解 |
| annotated-types | 0.7.0 | MIT | 类型注解 |
| anyio | 4.14.1 | MIT | 异步 IO 兼容层 |
| beautifulsoup4 | >=4.12.0,<5.0.0 | MIT | 扫榜 HTML 解析（`ranking_crawlers.py` 6 处扫描器 lazy import）；装包时随带传递依赖 `soupsieve`（MIT）—— 按 B-39 拍板，`soupsieve` 不单独列入 requirements |
| certifi ⚠️ | 2026.6.17 | MPL-2.0 | CA 根证书（TLS 必需基础设施） |
| charset-normalizer | 3.4.7 | MIT | 字符集探测 |
| click | 8.4.2 | BSD-3-Clause | CLI 框架 |
| colorama | 0.4.6 | BSD-3-Clause | 终端着色 |
| et_xmlfile | 2.0.0 | MIT | Excel XML 解析支撑 |
| faiss-cpu | 1.14.3 | MIT | 向量检索 |
| fastapi | 0.138.1 | MIT | Web 后端框架 |
| filelock | 3.29.0 | MIT | 文件锁 |
| fsspec | 2026.4.0 | BSD-3-Clause | 文件系统抽象 |
| h11 | 0.16.0 | MIT | HTTP/1.1 协议 |
| hf-xet | 1.5.1 | Apache-2.0 | HuggingFace 大文件传输 |
| httpcore | 1.0.9 | BSD-3-Clause | 底层 HTTP |
| httpx | 0.28.1 | BSD-3-Clause | HTTP 客户端 |
| huggingface_hub | 1.21.0 | Apache-2.0 | HF 模型/数据拉取 |
| idna | 3.18 | BSD-3-Clause | 域名编码 |
| jieba | 0.42.1 | MIT | 中文分词 |
| Jinja2 | 3.1.6 | BSD-3-Clause | 模板引擎 |
| joblib | 1.5.3 | BSD-3-Clause | 序列化/并行 |
| lxml | 6.1.1 | BSD-3-Clause | XML/HTML 解析 |
| markdown-it-py | 4.2.0 | MIT | Markdown 解析 |
| MarkupSafe | 3.0.3 | BSD-3-Clause | HTML 转义 |
| mdurl | 0.1.2 | MIT | Markdown 链接解析 |
| modelscope | 1.38.0 | Apache-2.0 | 魔搭模型/数据 |
| modelscope-hub | 0.1.6 | Apache-2.0 | 魔搭 Hub |
| mpmath | 1.3.0 | BSD-3-Clause | 任意精度数学 |
| narwhals | 2.22.1 | MIT | DataFrame 兼容层 |
| networkx | 3.6.1 | BSD-3-Clause | 图算法 |
| numpy | 2.4.6 | BSD-3-Clause | 数值计算 |
| openpyxl | 3.1.5 | MIT | Excel 读写 |
| packaging | 26.2 | Apache-2.0 | 版本/包解析 |
| pefile | 2024.8.26 | MIT | PE 文件解析 |
| pillow | 12.2.0 | HPND | 图像处理 |
| pydantic | 2.13.4 | MIT | 数据校验 |
| pydantic_core | 2.46.4 | MIT | pydantic 内核 |
| Pygments | 2.20.0 | BSD-2-Clause | 代码高亮 |
| pyinstaller ⚠️ | 6.21.0 | GPL-2.0-with-exception | 桌面端打包（构建期仅，非运行时） |
| pyinstaller-hooks-contrib | 2026.6 | MIT | pyinstaller 钩子 |
| PyPDF2 | 3.0.1 | BSD-3-Clause | PDF 解析 |
| python-docx | 1.2.0 | MIT | Word 文档 |
| python-multipart | 0.0.32 | MIT | 表单解析 |
| pywin32-ctypes | 0.2.3 | MIT | Windows API 封装 |
| PyYAML | 6.0.3 | MIT | YAML 解析 |
| regex | 2026.5.9 | Python-2.0 (permissive) | 正则引擎 |
| reportlab | 5.0.0 | BSD-3-Clause | PDF 生成 |
| requests | 2.34.2 | Apache-2.0 | HTTP 客户端 |
| rich | 15.0.0 | MIT | 终端富文本 |
| safetensors | 0.8.0 | Apache-2.0 | 张量安全存储 |
| scikit-learn | 1.9.0 | BSD-3-Clause | 机器学习 |
| scipy | 1.17.1 | BSD-3-Clause | 科学计算 |
| sentence-transformers | 5.6.0 | Apache-2.0 | 句向量模型 |
| shellingham | 1.5.4 | MIT | Shell 检测 |
| starlette | 1.3.1 | BSD-3-Clause | ASGI 框架（fastapi 底座） |
| sympy | 1.13.1 | BSD-3-Clause | 符号计算 |
| threadpoolctl | 3.6.0 | BSD-3-Clause | 线程控制 |
| tokenizers | 0.22.2 | Apache-2.0 | 分词器 |
| torch | 2.5.1 | BSD-3-Clause | 深度学习框架 |
| torchvision | 0.20.1 | BSD-3-Clause | 视觉模型 |
| tqdm ⚠️ | 4.68.3 | MPL-2.0 AND MIT | 进度条（双重许可，任选其一） |
| transformers | 5.12.1 | Apache-2.0 |  transformers 模型库 |
| typer | 0.25.1 | MIT | CLI 框架 |
| typing-inspection | 0.4.2 | MIT | 类型反射 |
| typing_extensions | 4.15.0 | PSF (permissive) | 类型扩展 |
| urllib3 | 2.7.0 | MIT | HTTP 底层 |
| uvicorn | 0.49.0 | BSD-3-Clause | ASGI 服务器 |
| pytest | >=8.0 | MIT | 测试框架（开发期） |
| pytest-asyncio | >=0.24 | MIT | 异步测试（开发期） |

## 自研零依赖模块（替代原第三方）

| 模块 | 替代对象 | 许可 |
|------|----------|------|
| `backend/services/epub_writer.py`（EpubWriter） | EbookLib（AGPL，已移除） | 书斋自研，MIT 兼容 |

## 禁止项（历史上已清除，不得 reintroduce）

- EbookLib（AGPL-3.0）——已被 `epub_writer.py` 取代。
- lengdu 系列（PolyForm Noncommercial）—— 已彻底移除并重写为 `shuzhai-*`。
- InkOS / ProseForge 痕迹 —— 已全部清零自研化，不允许再引入其源码/注释/常量。

## 新增依赖流程

1. 确认目标许可属于第 2 类（宽松）或第 3 类（已记录弱 Copyleft 例外）。
2. 在此表追加一行（含版本与许可）。
3. 加入 `requirements*.txt`。
4. 运行 `node tools/esm_gate.mjs`（含 `gate_license.py`）确认通过。
