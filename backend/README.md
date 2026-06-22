# MiCall 后端（四层防线 · 骨架）

按 `docs/02-后端架构与实现规格.md` + `docs/CLAUDE.md` 实现。本目录是**骨架**：四层防线的
结构、信令服务器、会话编排状态机、服务端权威计费、四层上下文组装、记忆数据模型、延迟 spike
工具全部到位且**可运行/可测**；外部供应商（ASR/LLM/TTS）走可插拔 provider 接口，骨架内置
stub 实现，真实实现待密钥接入（只改配置，不动对话逻辑 —— 铁律2）。

## 分层（对应 docs/02 的四个时间尺度）

```
src/micall/
  config.py              配置系统（铁律2：endpoint/key 全配置化 + 三级覆盖 §6.1）
  protocol.py            信令协议（对齐 docs/03 §4/§5 与前端 signaling.ts）
  providers/             ASR / LLM / TTS 可插拔接口 + stub + 真实骨架
  session/
    state.py             phase 状态机（idle→calling→listening→thinking→speaking→ended + 打断）
    orchestrator.py      会话编排：task A 感知 / B 思考生成 / C 发声 + 打断熔断（§1.3/§1.5）
    billing.py           服务端权威计费（§5，绝不信前端计时）
    emotion.py           情绪标签 piggyback 解析（§2.1，一处产生多处消费）
  context/
    models.py            用户画像 schema（理解层 §3.2：personality_model/open_hypotheses/relationship）
    assembler.py         四层 context 组装 + token 预算裁剪（§3.4）
  memory/
    repository.py        事实层 + 理解层仓储接口 + 内存实现（真实用 Postgres+pgvector）
    schema.sql           Postgres + pgvector 表结构
  server/
    wsserver.py          WebSocket 信令服务器（websockets 库），把会话编排接到前端
  spike/
    latency.py           尺度一延迟 spike（§1.6 / §8 钦定的"后端第一个动作"：实测 TTFT）
  cli.py                 入口：run-server / spike / initdb
```

## 运行

核心逻辑测试（零依赖，任何环境直接跑）：
```bash
cd backend && python3 -m tests
```

端到端冒烟（真起 WS 服务器 + 客户端走一遍协议；需 `pip install -r requirements.txt`）：
```bash
cd backend && PYTHONPATH=src python3 scripts/smoke_server.py
```

启动信令服务器（对接前端）：
```bash
cd backend && PYTHONPATH=src python3 -m micall.cli run-server
# 前端把 VITE_SIGNALING_URL 指向 ws://<host>:8787/realtime/signal 即从 Mock 切到真实后端
```

延迟 spike（实测某 LLM endpoint 的 TTFT；endpoint/key 从配置，铁律2）：
```bash
cd backend && PYTHONPATH=src python3 -m micall.cli spike --node llm_fast --prompt-tokens 2000
```

配置自检（看各节点 endpoint/key 是否就绪）：
```bash
cd backend && PYTHONPATH=src python3 -m micall.cli selfcheck
```

## 配置（铁律2）

`config/default.json` 是占位（**不含真实密钥**）。真实部署：
- 用 `MICALL_CONFIG=/path/to/secret.json` 指向含密钥的配置（不入库），或
- 用环境变量 `MICALL_LLM_FAST_API_KEY` 等逐项注入（优先级最高）。

切供应商（"先走 apiyi、卡了切直连 DeepSeek"）只改配置，对话逻辑不动。

## 骨架边界（明确未做，待真实接入）

- provider 的真实实现（apiyi/百炼/MiniMax HTTP 调用）写了骨架但默认用 stub；接密钥后启用。
- 实时媒体（WebRTC 音频上/下行）与 Pipecat/LiveKit 编排框架未接入：骨架的 orchestrator 用
  文本/stub 驱动同一套状态机与信令，媒体管线接入点已留好（providers + orchestrator hooks）。
- Postgres+pgvector：给了 schema.sql + 仓储接口 + 内存实现；真实连库用 asyncpg（requirements）。
- 离线理解引擎 worker、自主状态/时间推进（尺度三/四的离线部分）：数据模型与接口到位，
  worker 调度留接入点。
