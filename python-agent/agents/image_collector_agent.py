"""
Image Collector Agent —— 素材收集

输入：PRD + 架构方案
输出：[{url, category, description}]
行为：零 LLM 调用 —— 根据页面类型和功能清单按规则判断需要的图片类型，
      从模拟图片库返回素材（真实环境替换为 Pexels/Unsplash API）。
"""
from agents.agent_logging import log_agent_ok, log_agent_start
from state.code_gen_state import CodeGenState


MOCK_IMAGES: dict[str, list[dict]] = {
    "banner": [
        {"url": "https://picsum.photos/1200/400?random=1", "category": "banner", "description": "首页横幅"},
    ],
    "product": [
        {"url": "https://picsum.photos/300/300?random=2", "category": "product", "description": "商品图 1"},
        {"url": "https://picsum.photos/300/300?random=3", "category": "product", "description": "商品图 2"},
    ],
    "icon": [
        {"url": "https://picsum.photos/64/64?random=4", "category": "icon", "description": "图标"},
    ],
    "logo": [
        {"url": "https://picsum.photos/200/200?random=5", "category": "logo", "description": "Logo"},
    ],
    "illustration": [
        {"url": "https://picsum.photos/600/400?random=6", "category": "illustration", "description": "插画"},
    ],
    "avatar": [
        {"url": "https://picsum.photos/100/100?random=7", "category": "avatar", "description": "头像"},
    ],
}


def _determine_image_needs(prd: dict) -> list[str]:
    """根据 PRD 判断需要哪些类型的图片（纯规则，零 LLM）"""
    page_type = prd.get("page_type", "")
    features = [f.get("name", "") for f in prd.get("features", [])]
    all_text = page_type + " ".join(features)

    needs: set[str] = set()

    # banner：几乎所有页面都需要
    needs.add("banner")

    # 商品/产品
    if page_type == "e-commerce" or any(k in all_text for k in ["商品", "产品", "Product"]):
        needs.add("product")

    # 图标
    needs.add("icon")

    # Logo
    needs.add("logo")

    # 插画：落地页、博客
    if page_type in ("landing", "blog", "portfolio"):
        needs.add("illustration")

    # 头像：社交、用户相关
    if any(k in all_text for k in ["用户", "头像", "评论", "User", "Avatar"]):
        needs.add("avatar")

    return list(needs)


def image_collector_agent(state: CodeGenState) -> CodeGenState:
    """Image Collector Agent 主逻辑 —— 零 LLM 调用"""
    prd = state.get("prd") or state.get("existing_prd") or {}
    log_agent_start(
        "Image Collector",
        f"正在收集素材，page_type={prd.get('page_type', '-')} feature_count={len(prd.get('features', []))}",
    )
    needed_types = _determine_image_needs(prd)

    collected: list[dict] = []
    for img_type in needed_types:
        if img_type in MOCK_IMAGES:
            collected.extend(MOCK_IMAGES[img_type])

    state["images"] = collected
    log_agent_ok(
        "Image Collector",
        f"素材收集完成，image_count={len(collected)} categories={','.join(sorted(needed_types))}",
    )
    return state
