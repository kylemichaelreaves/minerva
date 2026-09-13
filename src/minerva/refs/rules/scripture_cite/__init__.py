"""Scripture-citation detection (Vulgate, Luther, KJV, Sacy).

The four language variants share one parametrized rule class —
:class:`._base.BaseScriptureCiteRule` — configured per language with
a lexicon, cite regex, and ambiguous-bare set.
"""

from ._base import BaseScriptureCiteRule
from .de import ScriptureCiteRuleDe
from .en import ScriptureCiteRuleEn
from .fr import ScriptureCiteRuleFr, ScriptureCiteRuleFrRoman, default_scripture_rules
from .lat import (
    FormulaicQuoteRule,
    ScriptureCiteRule,
    ScriptureCiteRuleLatRoman,
)
from .lexicon import _CITE_RE, _LEXICON, _sbl_abbr_for

__all__ = [
    "_CITE_RE",
    "_LEXICON",
    "BaseScriptureCiteRule",
    "FormulaicQuoteRule",
    "ScriptureCiteRule",
    "ScriptureCiteRuleDe",
    "ScriptureCiteRuleEn",
    "ScriptureCiteRuleFr",
    "ScriptureCiteRuleFrRoman",
    "ScriptureCiteRuleLatRoman",
    "_sbl_abbr_for",
    "default_scripture_rules",
]
