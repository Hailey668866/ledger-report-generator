from decimal import Decimal

SCATTER = "散采"
MONTH_TARGET = Decimal("1670000")  # noqa: FURB157
QUARTER_TARGET = Decimal("5000000")  # noqa: FURB157
CAPITAL_COST = Decimal("0.0448")
FUND_RATES = {
    "广州美鑫通国际供应链有限公司": Decimal("0.10"),
    "浙江飞速供应链管理有限公司": Decimal("0.12"),
}

OUZHANG = "欧展国际货运（上海）有限公司北京货运代理分公司"
YINHUA = "上海印华国际货运代理有限公司深圳分公司"
BUSINESS_RULES = (
    ("WWP", {"supplier": "Worldwide Partner Logistics Company Limited"}),
    ("欧展-固定位（LAX）", {"supplier": OUZHANG, "project_type": "BSA-欧展"}),
    ("欧展-差价", {"supplier": OUZHANG, "project_type": "差价-欧展"}),
    ("金开宇", {"supplier": "北京金开宇国际货运代理有限公司"}),
    ("厦门伦升", {"supplier": "厦门伦升国际物流有限公司"}),
    ("印华固定位OSL", {"supplier": YINHUA, "destination": "OSL"}),
    ("印华固定位ORD", {"supplier": YINHUA, "destination": "ORD"}),
    ("印华固定位LGG", {"supplier": YINHUA, "destination": "LGG"}),
    ("美鑫通GRU", {"supplier": "广州美鑫通国际供应链有限公司"}),
    ("迅達航空", {"supplier": "迅達航空貨運（香港）有限公司"}),
    ("散采", {"project_type": "散采"}),
)
