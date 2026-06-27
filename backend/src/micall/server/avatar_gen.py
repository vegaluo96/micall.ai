"""角色头像生成 —— 后台一键给角色生成「半写实·柔光影棚」头像（走 apiyi / OpenAI 兼容生图接口）。

防全站漂移的核心：构图 / 风格 / 背景 / 负向词全部【锁死】在本模块（运营改不了），只有「身份描述」
按角色 identity 字段变化。统一 1:1 正方、头肩居中、正面看镜头、干净柔背景 → 36 个角色放进同一个
圆里不漂移。生成的图存 avatars/{cid}.png，public_characters 带出 /api/avatar?c=cid。

接口：OpenAI 兼容 images/generations（apiyi 网关）。请求 {model,prompt,size,n}；不带 response_format
（gpt-image 默认回 b64、dall-e/flux 默认回 url，两种都兼容解析）。模型/尺寸由运营在『生图』节点配。
"""
from __future__ import annotations

import asyncio
import base64
import logging

log = logging.getLogger("micall.avatar")

# ── 锁死的规范（运营改不了，保证不漂移）──────────────────────────────────────────
# 风格：半写实·柔光影棚（用户已选定）。
_STYLE = (
    "semi-realistic soft studio portrait, gentle cinematic key light, refined elegant premium mood, "
    "natural skin texture, subtle film grain, shallow depth of field, high detail"
)
# 构图：每张一模一样的取景——头肩居中、眼睛在上三分线、头占 ~55%、正面看镜头。
_COMPOSITION = (
    "head-and-shoulders portrait, face horizontally centered, eyes on the upper-third line, "
    "head fills about 55 percent of the frame, even margin above the head, front-facing, "
    "looking straight at the camera, calm gentle natural expression, sharp focus on the eyes, 1:1 square"
)
# 背景：干净、低对比、统一柔背景——放进圆里边缘干净、各角色一致。
_BACKGROUND = (
    "clean soft low-contrast neutral studio gradient backdrop, smooth and slightly blurred, "
    "seamless, no scene, no props, no text"
)
# 负向词：杜绝文字/水印/手/全身/多人/裁脸/边框等破坏一致性的元素。
_NEGATIVE = (
    "text, watermark, logo, signature, caption, hands, full body, multiple people, extra faces, "
    "extreme angle, harsh shadows, cropped face, out of frame, border, frame, collage, deformed"
)

_GENDER_EN = {"男": "man", "女": "woman"}
_RACE_EN = {
    "东亚人": "East Asian", "亚洲人": "Asian", "中国": "Chinese", "中国人": "Chinese",
    "欧美": "Western", "白人": "Caucasian", "黑人": "Black", "拉丁": "Latino", "混血": "mixed-race",
}


def _en(table: dict, val: str) -> str:
    v = (val or "").strip()
    return table.get(v, v)


def build_prompt(spec: dict) -> str:
    """从角色 spec 的 identity 字段拼提示词。身份部分按角色变，其余（风格/构图/背景/负向）全锁死。"""
    ident = (spec or {}).get("identity", {}) or {}
    prof = ident.get("profile", {}) or {}
    gender = _GENDER_EN.get((ident.get("gender") or "").strip(), "person")
    age = ident.get("age") or prof.get("age") or ""
    bits: list[str] = []
    bits.append(f"a {age}-year-old {gender}" if str(age).strip() else f"a {gender}")
    race = _en(_RACE_EN, prof.get("race") or "") or _en(_RACE_EN, ident.get("nationality") or "")
    if race:
        bits.append(race)
    appearance = (ident.get("appearance") or "").strip()
    if appearance:
        bits.append(appearance)               # 长相（可中文）：模型据此定外貌
    occupation = (ident.get("occupation") or "").strip()
    if occupation:
        bits.append(f"the vibe of {occupation}")
    identity = ", ".join(bits)
    return f"{_STYLE}. Portrait of {identity}. {_COMPOSITION}. {_BACKGROUND}. Avoid: {_NEGATIVE}."


async def _do_generate(prompt: str, endpoint: str, api_key: str, model: str, size: str) -> bytes:
    import httpx

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict = {"prompt": prompt, "n": 1, "size": size or "1024x1024"}
    if model:
        body["model"] = model
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(endpoint, headers=headers, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"生图 HTTP {r.status_code} · {r.text[:300]}")
        try:
            d = r.json()
        except ValueError:
            raise RuntimeError(f"生图返回非 JSON：{r.text[:300]}")
        data = d.get("data") or []
        item = data[0] if data else {}
        b64 = item.get("b64_json")
        if b64:
            return base64.b64decode(b64)
        url = item.get("url")
        if url:
            r2 = await client.get(url)
            if r2.status_code >= 400:
                raise RuntimeError(f"下载生图 HTTP {r2.status_code}")
            return r2.content
        raise RuntimeError(f"生图未返回图片（无 b64_json / url）：{str(d)[:300]}")


def generate_for_character(character_id: str) -> dict:
    """给指定角色生成并保存头像。返回 {ok, avatar, error}。"""
    from ..config import load_config
    from .characters_admin import avatar_url, effective_specs, save_avatar

    cid = (character_id or "").strip()
    if not cid:
        return {"ok": False, "error": "缺少角色 id"}
    spec = effective_specs().get(cid)
    if not spec:
        return {"ok": False, "error": f"角色不存在：{cid}"}
    node = load_config().node("image")
    if not node.configured:
        return {"ok": False, "error": "『生图』节点未配置 endpoint/api_key（请先在「接口配置」里配好生图模型）"}
    model = str((node.params or {}).get("model") or "")
    size = str((node.params or {}).get("size") or "1024x1024")
    prompt = build_prompt(spec)
    try:
        img = asyncio.run(_do_generate(prompt, node.endpoint, node.api_key, model, size))
    except Exception as e:
        log.warning("头像生成失败 char=%s：%r", cid, e)
        return {"ok": False, "error": str(e)[:400]}
    if not img:
        return {"ok": False, "error": "生图返回空图片"}
    try:
        save_avatar(cid, img)
    except Exception as e:
        log.warning("头像保存失败 char=%s：%r", cid, e)
        return {"ok": False, "error": f"图已生成但保存失败：{str(e)[:200]}"}
    log.info("✅ 头像生成 char=%s（%d bytes, model=%s）", cid, len(img), model or "(默认)")
    return {"ok": True, "avatar": avatar_url(cid)}
