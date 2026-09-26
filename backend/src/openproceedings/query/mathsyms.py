"""Math spelled two ways, one token (decision-006, task-071).

Abstracts write the same math as LaTeX (`$\\alpha$`, `$\\times$`, `$n^2$`) or as Unicode (`α`, `×`, `n²`),
and OpenReview and the proceedings often differ. The token contract gives both spellings one token:

- **Greek letters** become the Unicode letter: `$\\alpha$` and `α` → `α` (a query must contain `α`).
- **Operators and relations** become the case-folded name of their LaTeX command: `×` and `$\\times$` →
  `times`, `≤`, `$\\le$` and `$\\leq$` → `leq`. A LaTeX alias maps to its operator's one name.
- **Super- and subscripts** join (NFKC's reading of `n²` is `n2`): see `normalize.py`, step 4.
"""

from __future__ import annotations

# LaTeX command (inside math) → Unicode Greek letter. Case is folded afterwards (`\Delta` → `δ`); the
# variant forms fold with NFKC (`ϵ` → `ε`, `ϑ` → `θ`, `ϕ` → `φ`, `ϖ` → `π`, `ϱ` → `ρ`; `ς` casefolds to `σ`).
GREEK: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "varkappa": "ϰ", "lambda": "λ",
    "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο", "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ",
    "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "ϕ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ",
    "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}  # fmt: skip

# Unicode operator or relation → its token: the case-folded name of its LaTeX command.
OPERATORS: dict[str, str] = {
    "×": "times", "·": "cdot", "⋅": "cdot", "÷": "div", "±": "pm", "∓": "mp",
    "≤": "leq", "⩽": "leq", "≥": "geq", "⩾": "geq", "≠": "neq", "≈": "approx", "≡": "equiv", "∼": "sim",
    "≃": "simeq", "≅": "cong", "∝": "propto", "≪": "ll", "≫": "gg",
    "→": "rightarrow", "⇒": "rightarrow", "←": "leftarrow", "⇐": "leftarrow", "↔": "leftrightarrow",
    "⇔": "leftrightarrow", "↦": "mapsto",
    "∈": "in", "∉": "notin", "∋": "ni", "⊂": "subset", "⊆": "subseteq", "⊃": "supset", "⊇": "supseteq",
    "∪": "cup", "∩": "cap", "∖": "setminus", "∅": "emptyset",
    "∀": "forall", "∃": "exists", "¬": "neg", "∧": "wedge", "∨": "vee",
    "⊕": "oplus", "⊗": "otimes", "⊙": "odot", "∘": "circ",
    "∞": "infty", "∑": "sum", "∏": "prod", "∫": "int", "∂": "partial", "∇": "nabla", "√": "sqrt",
    "∥": "parallel", "⊥": "perp",
}  # fmt: skip

# LaTeX commands (inside math) that are operators: each name and alias → the operator's token. The
# canonical names come from OPERATORS; the aliases spell the same symbol another way.
_ALIASES = {
    "le": "leq", "leqslant": "leq", "ge": "geq", "geqslant": "geq", "ne": "neq", "to": "rightarrow",
    "Rightarrow": "rightarrow", "implies": "rightarrow", "gets": "leftarrow", "Leftarrow": "leftarrow",
    "iff": "leftrightarrow", "Leftrightarrow": "leftrightarrow", "lnot": "neg", "land": "wedge",
    "lor": "vee", "varnothing": "emptyset",
}  # fmt: skip
OPERATOR_COMMANDS: dict[str, str] = {**{name: name for name in OPERATORS.values()}, **_ALIASES}
