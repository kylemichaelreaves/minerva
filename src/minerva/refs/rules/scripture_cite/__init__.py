"""Scripture-citation detection (Vulgate, Luther, KJV, Sacy)."""

from .de import ScriptureCiteRuleDe
from .en import ScriptureCiteRuleEn
from .fr import ScriptureCiteRuleFr, default_scripture_rules
from .lat import FormulaicQuoteRule, ScriptureCiteRule
from .lexicon import _CITE_RE, _LEXICON, _sbl_abbr_for

__all__ = [
    "_CITE_RE",
    "_LEXICON",
    "FormulaicQuoteRule",
    "ScriptureCiteRule",
    "ScriptureCiteRuleDe",
    "ScriptureCiteRuleEn",
    "ScriptureCiteRuleFr",
    "_sbl_abbr_for",
    "default_scripture_rules",
]
