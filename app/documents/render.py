"""Documents Kayé sends to merchants (receipts, invoices, reminders...), as Jinja HTML templates.

The same templates feed the design canvas (design/) and, later, the image renderer.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"


def fcfa(amount: int) -> str:
    """33000 -> '33 000' (narrow no-break space, French grouping). Amounts are integer FCFA."""
    return f"{amount:,}".replace(",", " ")


def make_env(asset_base: str = "/brand") -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        auto_reload=True,
    )
    env.filters["fcfa"] = fcfa
    env.globals["asset"] = lambda name: f"{asset_base}/{name}"
    return env


def render(template: str, data: dict, asset_base: str = "/brand") -> str:
    return make_env(asset_base).get_template(template).render(**data)
