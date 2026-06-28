"""世界上下文：每天全站批量拉一次「真实天气 + 安全时事话题」，所有角色共享，让 TA 像真活在世界里。

第一性原理：
  • 真人不在通话里现查——平时就知道天气、刷到点新鲜事，聊时自然带出。故全部【离线·每天一批】，零通话延迟。
  • 相关性（"角色相关"）在【说话时】免费发生、不在【抓取时】花钱：抓一池【多样】的安全话题（全站共享、1 次/天），
    每个角色按自己人设挑感兴趣的聊——便宜且自然。
  • 数据分两路：天气 = open-meteo（免费、准、每城一次）；时事话题 = 联网脑（grok 等，1 次/天全站共享）。
  • 安全是命门：话题必过安全闸（去政治/灾难/负面/敏感），且永远由角色用家常口吻重述，绝不直给用户。
拉不到一律降级（天气→慢脑季节推测；话题→无），绝不影响实时。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

from .understanding import parse_profile_update

try:  # open-meteo 走 httpx；缺失则天气功能静默降级
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

log = logging.getLogger("micall.world")

_SEARCH_TIMEOUT_S = 30.0   # 联网拉话题单次兜底超时（离线）
_WEATHER_TIMEOUT_S = 8.0   # open-meteo 单次超时

# 安全闸：抓回的真实世界内容命中这些就整条丢弃（陪伴产品里角色嘴一歪就是事故，尤其国内合规）。
_UNSAFE = (
    "政治", "时政", "政府", "领导", "主席", "总统", "总理", "书记", "党", "官员", "选举", "议会", "两会", "讲话",
    "抗议", "游行", "示威", "罢工", "war", "战争", "冲突", "军事", "导弹", "核武", "制裁",
    "灾难", "地震", "海啸", "洪水", "山火", "火灾", "爆炸", "坍塌", "事故", "车祸", "空难", "坠机", "坠楼",
    "死亡", "身亡", "遇难", "丧生", "伤亡", "遗体", "尸", "自杀", "凶", "杀", "命案", "枪", "恐怖", "暴力",
    "疫情", "病毒", "确诊", "封控", "瘟疫",
    "股市", "股票", "暴跌", "崩盘", "暴雷", "破产", "裁员", "失业", "经济危机", "通胀", "金融危机",
    "毒品", "涉黄", "色情", "赌", "诈骗", "犯罪", "案件", "判刑", "逮捕", "丑闻", "维权", "敏感",
    "习", "modi", "trump", "biden", "putin",
)


def _is_safe(text: str) -> bool:
    """无敏感/负面命中才算安全。空串不安全。纯函数，便于测试。"""
    t = (text or "").lower()
    return bool(t.strip()) and not any(bad in t for bad in _UNSAFE)


def _date(now: datetime.datetime) -> str:
    return f"{now.year}-{now.month:02d}-{now.day:02d}"


def clean_city(raw: str) -> str:
    """从 identity.residence 取一个干净城市名（去「现居」前缀/区县后缀），供天气查询与去重。取不到返回 ""。"""
    raw = re.sub(r"^现居[于在]?", "", str(raw or "").strip()).strip()
    raw = re.split(r"[·,，、/\s]", raw)[0].strip()
    return raw[:20]


# ── 天气：open-meteo（免费、无 key、全球；中文地名走其 geocoding）──────────────────────
_WMO = {
    0: "晴", 1: "大致晴朗", 2: "多云", 3: "阴", 45: "有雾", 48: "雾凇",
    51: "细毛毛雨", 53: "毛毛雨", 55: "较大毛毛雨", 56: "冻毛毛雨", 57: "较强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "较强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪",
    80: "阵雨", 81: "较强阵雨", 82: "强阵雨", 85: "小阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}
_RAINY = frozenset({51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99})


def _feel(temp: float | None, code: int) -> str:
    if not isinstance(temp, (int, float)):
        return ""
    if temp <= 3:
        return "，挺冷"
    if temp <= 10:
        return "，凉"
    if temp >= 32:
        return "，挺热"
    if temp >= 28:
        return "，有点闷热"
    return "，湿乎乎" if code in _RAINY else ""


def _weather_line(city: str, temp: float | None, code: int) -> str:
    """纯函数：把 open-meteo 取到的温度/天气码拼成一句中文天气。便于测试。"""
    desc = _WMO.get(code, "")
    t = f"{round(temp)}°C" if isinstance(temp, (int, float)) else ""
    body = "，".join([b for b in (desc, t) if b])
    if not body:
        return ""
    return (f"今天{city}{body}{_feel(temp, code)}").strip("，")


def _client() -> "httpx.AsyncClient":
    from ..providers._http import loop_client, pool_limits
    return loop_client(lambda: httpx.AsyncClient(
        timeout=httpx.Timeout(_WEATHER_TIMEOUT_S, connect=5.0), limits=pool_limits()))


async def fetch_weather(city: str) -> dict | None:
    """open-meteo 查 city 当前真实天气 → {line, temp, code}。无 httpx/city/失败 → None（降级到季节推测）。
    返回结构化（不只一句话）：温度/天气码留着喂【天气连续性】（昨天 vs 今天的变化感）。免费、无 key。"""
    if httpx is None or not city:
        return None
    try:
        cl = _client()
        g = await asyncio.wait_for(cl.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"}), timeout=_WEATHER_TIMEOUT_S)
        g.raise_for_status()
        res = (g.json().get("results") or [])
        if not res:
            return None
        lat, lon = res[0].get("latitude"), res[0].get("longitude")
        f = await asyncio.wait_for(cl.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"}),
            timeout=_WEATHER_TIMEOUT_S)
        f.raise_for_status()
        cur = f.json().get("current") or {}
        temp = cur.get("temperature_2m")
        try:
            code = int(cur.get("weather_code", -1))
        except (TypeError, ValueError):
            code = -1
        line = _weather_line(city, temp, code)
        if not line:
            return None
        return {"line": line, "temp": temp if isinstance(temp, (int, float)) else None, "code": code}
    except Exception as e:
        log.info("open-meteo 天气拉取失败 city=%s：%r", city, e)
        return None


# ── 时事话题：从【免费无注册热榜 API】抓【真实热点】(标题+原文链接) → 过安全闸 → LLM(qwen-long)
#    【grounded 改写】成口语闲聊。第一性原理：真实性来自【真实数据源】，不靠模型"联网"——
#    让 LLM 凭空"联网找热点"只会编（grok-4.3/qwen-long 都没有真·网络检索）。这里 LLM 只当【改写器】：
#    输入真实标题、输出口语说法，绝不新增/编造事实。每条都带【原文链接】，后台可点开核对、铁证是真的。
# 一批【免费、无注册、稳定】的热点/内容源（都是资产，越多越广越不尬；某个挂了其它顶上）。
# 关键：以【全球可达·不挑地区语言】的国际源为主——国产域名(vvhan/imsyy)从香港机房常解析不到(DNS)，
# Reddit 的 .json 从机房 IP 常被 403 拦——故主力换成【RSS 订阅源】：几乎每家媒体都有、免注册、全球可达、
# 维度极广（科技/影视/游戏/科学/音乐/美食/旅行/趣闻…）。RSS 是 XML，_fetch_generic 先试 JSON、失败再当 RSS 解。
# 外文内容由【改写脑】翻译成中文口语并兼做安全闸。全部含 title/url、由 _iter_hot_records / _parse_rss 通吃。
_HOT_ENDPOINTS_DEFAULT = (
    # JSON·全球可达·免 key
    "https://dev.to/api/articles?top=7",                          # 科技/开发
    "https://lobste.rs/hottest.json",                             # 科技
    # RSS·全球可达·免注册·维度广（主力，每家媒体都有、极稳）
    "https://www.theverge.com/rss/index.xml",                     # 科技/数码
    "https://feeds.arstechnica.com/arstechnica/index",           # 科技/科学
    "https://www.sciencedaily.com/rss/top/science.xml",          # 科学
    "https://www.polygon.com/rss/index.xml",                     # 游戏
    "https://feeds.feedburner.com/ign/games-all",                # 游戏
    "https://pitchfork.com/feed/feed-news/rss",                  # 音乐
    "https://www.eater.com/rss/index.xml",                       # 美食
    "https://www.atlasobscura.com/feeds/latest",                 # 旅行/趣闻
    "https://www.mentalfloss.com/feeds/all",                     # 冷知识/趣闻
    "https://lithub.com/feed/",                                   # 读书/文学
    "https://www.smithsonianmag.com/rss/latest_articles/",       # 人文/科普
    # 国产·DNS 能解析到时才用（香港机房常解析不到 → 自动跳过，不影响其它源）
    "https://api.vvhan.com/api/hotlist/all",
    "https://api-hot.imsyy.top/all",
)
# Hacker News（Firebase，全球可达、免 key、极稳）：需两步（topstories→item）。
_HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
# 维基百科（REST v1，免 key，全球可达）：隽永/知识类素材，中英双语，真实可核对。
_WIKI_ONTHISDAY = "https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/selected/{mm}/{dd}"  # 历史上的今天
_WIKI_FEATURED = "https://{lang}.wikipedia.org/api/rest_v1/feed/featured/{yyyy}/{mm}/{dd}"        # 今日热门词条
_WIKI_LANGS = ("zh", "en")
_HOT_TIMEOUT_S = 12.0
# 维基百科强制要求【带联系方式】的 User-Agent，否则 403（policy: meta.wikimedia.org/wiki/User-Agent_policy）。
_UA = "MiCallBot/1.0 (+https://zsky.com; AI companion world-context) python-httpx"
_TITLE_KEYS = ("title", "word", "query", "hotword", "keyword", "desc")
_URL_KEYS = ("url", "mobileUrl", "mobilUrl", "link", "href")


def _iter_hot_records(obj: Any):
    """深度遍历任意热榜 API 的 JSON，抠出 {title, url} 条目。兼容 vvhan/imsyy/微博式等多种 schema。
    只认 title/word/query… 当标题（不认 name/subtitle，避免把『平台名』当成热点）。纯函数、便于测试。"""
    if isinstance(obj, dict):
        title = next((obj[k] for k in _TITLE_KEYS if isinstance(obj.get(k), str) and obj[k].strip()), "")
        if title:
            url = next((obj[k] for k in _URL_KEYS if isinstance(obj.get(k), str) and obj[k].strip()), "")
            yield {"title": title.strip()[:120], "url": str(url or "").strip()}
        for v in obj.values():
            if isinstance(v, (list, dict)):
                yield from _iter_hot_records(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_hot_records(v)


def _parse_wiki_onthisday(data: Any) -> list[dict]:
    """从维基『历史上的今天』REST 响应抠出 [{title, url}]：标题=『X年的今天，<事件>』、url=词条页。纯函数。"""
    out: list[dict] = []
    evs = (data.get("selected") or data.get("events") or []) if isinstance(data, dict) else []
    for ev in evs:
        if not isinstance(ev, dict):
            continue
        text = str(ev.get("text") or "").strip()
        if not text:
            continue
        year = ev.get("year")
        pages = ev.get("pages") or []
        url = ""
        if pages and isinstance(pages[0], dict):
            url = (((pages[0].get("content_urls") or {}).get("desktop") or {}).get("page")) or ""
        title = f"{year}年的今天，{text}" if isinstance(year, int) else f"历史上的今天，{text}"
        out.append({"title": title[:120], "url": str(url or "")})
    return out


def _has_cjk(s: str) -> bool:
    """含中日韩汉字 → True。没改写脑(不翻译)时只用中文标题；外文无法翻译/无法用中文关键词闸 vet，丢弃。"""
    return bool(re.search(r"[一-鿿]", s or ""))


def _local(tag: str) -> str:
    """剥掉 XML 命名空间前缀，只留本地标签名（RSS/Atom 命名空间五花八门，按 local-name 匹配最稳）。"""
    return tag.rsplit("}", 1)[-1].lower()


def _parse_rss(text: str) -> list[dict]:
    """解析 RSS/Atom XML → [{title, url}]。兼容 RSS<item><title><link>text 与 Atom<entry><title><link href>。
    命名空间无关（按 local-name 匹配）。无法解析/无条目 → []。纯函数、便于测试。"""
    try:
        root = ET.fromstring(text)
    except Exception:
        return []
    out: list[dict] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title, url = "", ""
        for ch in node:
            lt = _local(ch.tag)
            if lt == "title" and not title:
                title = "".join(ch.itertext()).strip()
            elif lt == "link" and not url:
                url = (ch.get("href") or ch.text or "").strip()   # Atom 用 href 属性、RSS 用文本
        if title:
            out.append({"title": title[:120], "url": url})
    return out


async def _fetch_generic(cl: Any, ep: str) -> list[dict]:
    r = await asyncio.wait_for(cl.get(ep, headers={"User-Agent": _UA}), timeout=_HOT_TIMEOUT_S)
    r.raise_for_status()
    try:
        return list(_iter_hot_records(r.json()))   # 先按 JSON 热榜解
    except Exception:
        return _parse_rss(r.text)                   # 失败 → 当 RSS/Atom XML 解（媒体订阅源）


async def _fetch_hackernews(cl: Any, top_n: int = 15) -> list[dict]:
    """Hacker News：先取 topstories 的 id 列表，再【并发】取每条 item 的 {title,url}。全球可达、免 key、极稳。"""
    r = await asyncio.wait_for(cl.get(_HN_TOP, headers={"User-Agent": _UA}), timeout=_HOT_TIMEOUT_S)
    r.raise_for_status()
    ids = (r.json() or [])[:top_n]

    async def _one(i: int) -> dict | None:
        try:
            ri = await asyncio.wait_for(cl.get(_HN_ITEM.format(id=i), headers={"User-Agent": _UA}),
                                        timeout=_HOT_TIMEOUT_S)
            ri.raise_for_status()
            d = ri.json() or {}
            t = str(d.get("title") or "").strip()
            if t:
                return {"title": t[:120], "url": str(d.get("url") or f"https://news.ycombinator.com/item?id={i}")}
        except Exception:
            return None
        return None

    got = await asyncio.gather(*[_one(i) for i in ids])
    return [x for x in got if x]


def _parse_wiki_mostread(data: Any) -> list[dict]:
    """从维基『今日精选』里抠出【今日最多人查的词条】→ [{title, url}]：标题=『最近不少人在查「X」：<简介>』。纯函数。"""
    out: list[dict] = []
    arts = ((data.get("mostread") or {}).get("articles") or []) if isinstance(data, dict) else []
    for a in arts:
        if not isinstance(a, dict):
            continue
        title = str(a.get("normalizedtitle") or a.get("title") or "").replace("_", " ").strip()
        if not title:
            continue
        url = (((a.get("content_urls") or {}).get("desktop") or {}).get("page")) or ""
        extract = str(a.get("extract") or "").strip()
        text = f"最近不少人在查「{title}」" + (f"：{extract[:36]}" if extract else "")
        out.append({"title": text[:120], "url": str(url or "")})
    return out


async def _fetch_wiki(cl: Any, now: datetime.datetime, lang: str = "zh") -> list[dict]:
    url = _WIKI_ONTHISDAY.format(lang=lang, mm=f"{now.month:02d}", dd=f"{now.day:02d}")
    r = await asyncio.wait_for(cl.get(url, headers={"User-Agent": _UA}), timeout=_HOT_TIMEOUT_S)
    r.raise_for_status()
    return _parse_wiki_onthisday(r.json())


async def _fetch_wiki_mostread(cl: Any, now: datetime.datetime, lang: str = "zh") -> list[dict]:
    url = _WIKI_FEATURED.format(lang=lang, yyyy=now.year, mm=f"{now.month:02d}", dd=f"{now.day:02d}")
    r = await asyncio.wait_for(cl.get(url, headers={"User-Agent": _UA}), timeout=_HOT_TIMEOUT_S)
    r.raise_for_status()
    return _parse_wiki_mostread(r.json())


def _world_jobs(cl: Any, endpoints: Any, now: datetime.datetime | None, wiki: bool):
    """构造所有数据源的 (标签, 协程) 任务列表（热榜 + Hacker News + 维基中英）。供并发抓取/逐源体检共用。"""
    jobs: list[tuple[str, Any]] = [(ep, _fetch_generic(cl, ep)) for ep in (endpoints or _HOT_ENDPOINTS_DEFAULT)]
    jobs.append(("Hacker News", _fetch_hackernews(cl)))
    if wiki and now is not None:
        for lang in _WIKI_LANGS:
            jobs.append((f"维基{lang}·历史上的今天", _fetch_wiki(cl, now, lang)))
            jobs.append((f"维基{lang}·今日热门词条", _fetch_wiki_mostread(cl, now, lang)))
    return jobs


async def fetch_hot_items(endpoints: Any = None, limit: int = 60,
                          now: datetime.datetime | None = None, wiki: bool = True) -> list[dict]:
    """【并发】拉所有免费数据源真实素材 → [{title, url}]（按标题去重）：国际热榜 + Hacker News + 维基(中英)。
    并发(gather)让源再多也不慢；某个挂了 return_exceptions 兜住、其它顶上。无 httpx/全失败 → []。免 key、免注册。"""
    if httpx is None:
        return []
    cl = _client()
    jobs = _world_jobs(cl, endpoints, now, wiki)
    results = await asyncio.gather(*[c for _, c in jobs], return_exceptions=True)
    seen: set[str] = set()
    items: list[dict] = []
    for res in results:
        if isinstance(res, BaseException):
            log.info("数据源拉取失败：%r", res)
            continue
        for rec in res:
            t = rec.get("title", "")
            if t and t not in seen:
                seen.add(t)
                items.append(rec)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return items[:limit]


async def probe_sources(endpoints: Any = None, now: datetime.datetime | None = None) -> list[dict]:
    """【并发】逐源测试可达性 + 拿到几条 + 过安全闸剩几条 + 2 条样例（含链接）。给后台「测试热点源」按钮，可据此增删源。"""
    if httpx is None:
        return [{"source": "httpx", "ok": False, "error": "缺少 httpx 依赖"}]
    cl = _client()
    when = now or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

    async def _probe(label: str, coro: Any) -> dict:
        try:
            recs = await coro
            safe = [r for r in recs if _is_safe(r.get("title", ""))]
            return {"source": label, "ok": True, "count": len(recs), "safe": len(safe),
                    "sample": [{"text": r["title"][:60], "url": r.get("url", "")} for r in safe[:2]]}
        except Exception as e:
            return {"source": label, "ok": False, "error": str(e)[:200]}

    jobs = _world_jobs(cl, endpoints, when, True)
    return list(await asyncio.gather(*[_probe(lbl, c) for lbl, c in jobs]))


def _rewrite_prompt(titles: list[str]) -> list[dict]:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    sys = (
        "下面是今天来自各处的【真实热搜/热门标题】（中英文混合），给一群【中文】虚拟陪伴角色当聊天话题。逐条处理：\n"
        "• 适合轻松闲聊的 → 【翻译成中文（若是外文）并改写成口语闲聊】，15~40 字，忠于原意、绝不新增/编造/夸大；\n"
        "• 涉及政治/时政/领导人/灾难/事故/死亡/暴力/血腥/色情/犯罪/疾病/股市/负面/敏感的 → 那一条输出空字符串 \"\""
        "（直接丢弃，不要翻译、不要改写）；\n"
        "• 看不懂、太小众、或不适合闲聊的 → 也输出 \"\"。\n"
        "严格只输出 JSON：{lines:[...]}，lines 的【条数和顺序必须与输入完全一致】，逐条一一对应（丢弃的位置放 \"\"）。"
    )
    user = f"真实标题（按编号）：\n{numbered}\n\n逐条处理（翻译+改写或丢弃），条数顺序与上面完全一致。"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


async def fetch_topics(rewrite_llm: Any, now: datetime.datetime, endpoints: Any = None) -> list[dict]:
    """真实热点话题池（全站共享）：免费数据源抓真实热点 → 过安全闸 → 改写脑【翻译成中文口语 + 兼做安全闸】。
    返回 [{text, url}]（最多 14，带原文链接）。改写脑只翻译/改写、不"找热点"——真实性来自数据源，绝不编。
    没配改写脑：外文无法翻译、也无法用中文关键词闸 vet → 只用中文标题原样（仍真实、仍安全）。"""
    items = await fetch_hot_items(endpoints, now=now)
    safe = [it for it in items if _is_safe(it["title"])]        # 先过中文关键词安全闸（对外文几乎不拦，靠下面改写脑兜）

    def _cn_only(src: list[dict]) -> list[dict]:
        return [{"text": it["title"][:90], "url": it["url"]} for it in src if _has_cjk(it["title"])][:14]

    if not safe:
        return []
    if rewrite_llm is None:
        return _cn_only(safe)                                   # 无改写脑 → 只用中文标题（外文丢弃，安全）
    cand = safe[:24]                                            # 多给候选，改写脑会丢掉不安全/不合适的，留够 ~14
    titles = [it["title"] for it in cand]
    try:
        async def _run() -> str:
            return "".join([t async for t in rewrite_llm.stream(
                _rewrite_prompt(titles), max_tokens=2000, response_format={"type": "json_object"})])
        raw = await asyncio.wait_for(_run(), timeout=_SEARCH_TIMEOUT_S)
        lines = [str(x).strip() for x in (parse_profile_update(raw).get("lines") or [])]
        if len(lines) == len(titles):                          # 对齐成功：丢弃的位置是 ""，跳过它、其余配 URL
            out: list[dict] = []
            for text, it in zip(lines, cand):
                if text and _is_safe(text):                    # 改写后再过一道中文关键词闸
                    out.append({"text": text[:90], "url": it["url"]})
                if len(out) >= 14:
                    break
            return out
    except Exception as e:
        log.info("热点改写失败（回退中文真实标题）：%r", e)
    return _cn_only(cand)                                       # 改写失败/不对齐 → 回退中文真实标题（外文没翻译没法用）


# ── 全站共享世界库（内存，按天）：每天批量刷一次，角色只读、零联网 ────────────────────────
#  weather       : {city: line}            今天每城的天气一句话（快读）
#  weather_hist  : {city: [{date,temp,code}…]}  最近几天的滚动观测——【天气连续性】的底料（昨天 vs 今天）
#  topics        : [str]                   今天的真实热点话题池（已改写成口语，给 assembler/Layer C 用）
#  topics_src     : [{text,url}]            同一池子带【原文链接】（后台展示、可点开核对真实性）
_WORLD: dict[str, Any] = {"date": "", "weather": {}, "weather_hist": {}, "topics": [], "topics_src": []}
_HIST_DAYS = 4   # 每城最多留几天观测（够算「这两天/前两天」的变化感即可，不堆历史）

# 世界库落盘路径：让【天气滚动历史】跨进程重启存活——否则每次重启只有「今天」、永远算不出「昨天→今天」的变化。
# 空=禁用持久化（默认；单测不落盘）。由 configure_store 启用（wsserver 启动时按 config 设）。
_STORE_PATH: str = ""


def configure_store(path: str) -> None:
    """启用世界库磁盘持久化（天气滚动历史跨重启存活 → 连续性才真成立）。空路径=禁用。启用时立刻从盘载入既有历史。"""
    global _STORE_PATH
    _STORE_PATH = (path or "").strip()
    _load_store()


def _load_store() -> None:
    if not _STORE_PATH:
        return
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(d, dict):
        return
    for k in ("date", "weather", "weather_hist", "topics", "topics_src"):
        if k in d and isinstance(d[k], type(_WORLD[k])):
            _WORLD[k] = d[k]


def _save_store() -> None:
    if not _STORE_PATH:
        return
    try:
        parent = os.path.dirname(_STORE_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = _STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_WORLD, f, ensure_ascii=False)
        os.replace(tmp, _STORE_PATH)
    except OSError as e:   # 落盘失败不影响运行（顶多重启后连续性少一天）
        log.info("世界库落盘失败（不影响运行）：%r", e)


def _record_weather(city: str, date_str: str, obs: dict) -> None:
    """把今天这城的观测并进滚动历史（同日去重覆盖，最多留 _HIST_DAYS 天），供天气连续性比对。"""
    hist = _WORLD["weather_hist"].setdefault(city, [])
    hist[:] = [h for h in hist if h.get("date") != date_str]
    hist.append({"date": date_str, "temp": obs.get("temp"), "code": obs.get("code")})
    if len(hist) > _HIST_DAYS:
        hist[:] = hist[-_HIST_DAYS:]


async def refresh_world(cities: list[str], now: datetime.datetime, search_llm: Any = None,
                        hot_endpoints: Any = None) -> dict:
    """全站每日批量：逐城拉真实天气(open-meteo,免费,并入滚动历史) + 从免费热榜 API 抓真实热点(带原文链接,
    LLM 仅 grounded 改写) → 写共享库+落盘。返回计数。"""
    date_str = _date(now)
    weather: dict[str, str] = {}
    seen: set[str] = set()
    for c in cities:
        c = (c or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        obs = await fetch_weather(c)
        if obs:
            weather[c] = obs["line"]
            _record_weather(c, date_str, obs)   # 连续性底料：记下今天的温度/天气码
    topics_src = await fetch_topics(search_llm, now, hot_endpoints)   # [{text,url}] 真实热点
    topics = [t["text"] for t in topics_src]
    _WORLD["date"], _WORLD["weather"] = date_str, weather
    _WORLD["topics"], _WORLD["topics_src"] = topics, topics_src
    _save_store()
    log.info("🌍 世界库刷新：%d 城真实天气 + %d 条真实热点（date=%s）", len(weather), len(topics), date_str)
    return {"cities": len(weather), "topics": len(topics)}


def _fresh(now: datetime.datetime) -> bool:
    return _WORLD["date"] == _date(now)


# ── 天气连续性（Layer A）：真人注意的是天气怎么【变】了，不是绝对值 ──────────────────────────
def _trend_phrase(pt: Any, pc: Any, t: Any, c: Any) -> str:
    """纯函数：由（前一天温度/码, 今天温度/码）拼一句【变化感】。无明显变化 → ""。便于测试。"""
    pr, nr = (pc in _RAINY), (c in _RAINY)
    if pr and not nr:
        return "前两天阴雨，今天总算放晴"
    if not pr and nr:
        return "昨天还好好的，今天又下起来了"
    if pr and nr:
        return "这雨断断续续下了好几天"
    if isinstance(pt, (int, float)) and isinstance(t, (int, float)):
        d = t - pt
        if d >= 5:
            return "比前两天暖和了不少"
        if d <= -5:
            return "比前两天凉了不少"
    return ""


def weather_trend(city: str, now: datetime.datetime) -> str:
    """读滚动历史，把 city【今天 vs 前一天】的变化拼成一句连续感。不足两天/过期 → ""。零联网。"""
    if not city or not _fresh(now):
        return ""
    hist = _WORLD["weather_hist"].get(city, [])
    today_str = _date(now)
    today = next((h for h in reversed(hist) if h.get("date") == today_str), None)
    prev = next((h for h in reversed(hist) if h.get("date") != today_str), None)
    if not today or not prev:
        return ""
    return _trend_phrase(prev.get("temp"), prev.get("code"), today.get("temp"), today.get("code"))


def weather_for(city: str, now: datetime.datetime) -> str:
    """读共享库里 city 今天的真实天气；无/过期 → ""。零联网。"""
    return _WORLD["weather"].get(city, "") if (city and _fresh(now)) else ""


def topics_now(now: datetime.datetime) -> list[str]:
    """读共享库里今天的时事话题池（全站共享）；无/过期 → []。零联网。"""
    return list(_WORLD["topics"]) if _fresh(now) else []


def world_snapshot(now: datetime.datetime) -> dict:
    """给后台「世界库」面板的只读快照：当前【已保存】的日期/话题/各城天气 + 是否当天新鲜 + 是否已开持久化 +
    每城历史天数（连续性底料厚度）。读的是持久化那份，重启/重新部署都还在。零联网。"""
    fresh = _fresh(now)
    return {
        "date": _WORLD.get("date", ""),
        "fresh": bool(fresh),                    # 今天是否已刷新（过期=昨天的，前端提示该拉新的）
        "persisted": bool(_STORE_PATH),          # 是否已开磁盘持久化（开了才跨重启不丢）
        "topics": list(_WORLD.get("topics") or []) if fresh else [],
        # 带原文链接的真实热点（后台可点开核对——这是话题"真不真"的铁证）
        "topics_src": [{"text": str(t.get("text", "")), "url": str(t.get("url", ""))}
                       for t in (_WORLD.get("topics_src") or []) if isinstance(t, dict)] if fresh else [],
        "weather": [{"city": c, "line": ln} for c, ln in (_WORLD.get("weather") or {}).items()] if fresh else [],
        "hist_days": {c: len(v) for c, v in (_WORLD.get("weather_hist") or {}).items()},
    }
