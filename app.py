import json
import re
from typing import List, Dict, Any

import streamlit as st


# =====================
# TEXT UTILITIES
# =====================

# --- Search trigger state for Enter key ---
if "run_search" not in st.session_state:
    st.session_state["run_search"] = False


def _trigger_search():
    # Called when user presses Enter in the search box
    st.session_state["run_search"] = True

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\sğüşiöç]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return normalize(text).split(" ")


def score_text_relevance(query_tokens: List[str], text: str) -> int:
    norm = normalize(text)
    text_tokens = set(norm.split(" "))
    return sum(1 for t in query_tokens if t in text_tokens)


# =====================
# INTENT DETECTION
# =====================

# Multi-word phrases that strongly indicate sustainability intent
ECO_PHRASES = [
    # Turkish
    "çevre dostu",
    "sürdürülebilir",
    "organik",
    "doğa dostu",
    # English
    "eco friendly",
    "environmentally friendly",
    "green product",
    "green furniture",
]

# Single-word tokens that indicate sustainability intent
ECO_TOKENS = [
    # Turkish
    "eko",
    "ekolojik",
    "sürdürülebilir",
    "organik",
    # English
    "eco",
    "sustainable",
    "green",
]


def detect_eco_intent(raw_query: str) -> dict:
    normalized = normalize(raw_query)
    tokens = normalized.split(" ")

    eco_intent = any(p in normalized for p in ECO_PHRASES)
    if not eco_intent:
        eco_intent = any(t in tokens for t in ECO_TOKENS)

    return {
        "raw_text": raw_query,
        "normalized_text": normalized,
        "tokens": tokens,
        "eco_intent": eco_intent,
    }


# =============================
# SUSTAINABILITY KEYWORDS
# (inside product descriptions)
# =============================

ECO_DESC_KEYWORDS = [
    # Turkish sustainability signals likely to appear in descriptions
    "geri dönüştürülmüş ahşap",
    "geri dönüştürülmüş",
    "organik boya",
    "organik pamuk",
    "organik keten",
    "sürdürülebilir kumaş",
    "su bazlı boya",
    "düşük voc",
    "fsc sertifikalı",
    "doğal lateks",
]


def has_eco_keywords(description: str) -> bool:
    desc_norm = normalize(description)
    return any(phrase in desc_norm for phrase in ECO_DESC_KEYWORDS)


# =============================
# LLM CLASSIFICATION (STUB)
# =============================

LLM_PROMPT_TEMPLATE = """You are a strict classifier.

TASK:
Decide if this furniture product is environmentally friendly based ONLY on its description (may be in Turkish).

ENVIRONMENTALLY FRIENDLY = description clearly mentions at least ONE of:
- recycled or reclaimed materials
- sustainable or certified sourcing
- organic or low-impact finishes
- reduced environmental impact of materials or production

If condition is met, answer EXACTLY:
YES

If condition is NOT met, answer EXACTLY:
NO

Answer with a single word only. Do not add any other text.

Description:
{description}
"""


def build_llm_prompt(description: str) -> str:
    return LLM_PROMPT_TEMPLATE.format(description=description.strip())


class DummyLLMClient:
    """
    Minimal stand-in for a real LLM client.
    For this prototype, we approximate the LLM decision using the same eco keywords.
    Replace `.complete` with a real API call when integrating an actual LLM.
    """

    def complete(self, prompt: str) -> str:
        desc = prompt.split("Description:", 1)[-1]
        return "YES" if has_eco_keywords(desc) else "NO"


def classify_eco_llm(description: str, llm_client: DummyLLMClient) -> bool:
    prompt = build_llm_prompt(description)
    raw = llm_client.complete(prompt).strip().upper()
    return raw == "YES"


# =============================
# HYBRID SEARCH LOGIC
# =============================

def run_search(products: List[Dict[str, Any]], raw_query: str, llm_client: DummyLLMClient) -> List[Dict[str, Any]]:
    """
    Hybrid search:
    - Detect sustainability intent (TR + EN).
    - If eco intent:
        * Use sustainability keywords in descriptions.
        * Use LLM classification.
        * Rank by: priority_score = keyword_match * 2 + llm_match
          where keyword_match and llm_match are 0/1.
    - If no eco intent:
        * Use simple keyword relevance on name + description.
    Returns a list of product dicts in ranked order.
    """
    parsed = detect_eco_intent(raw_query)
    eco_intent = parsed["eco_intent"]
    tokens = parsed["tokens"]

    ranked: List[Dict[str, Any]] = []

    for product in products:
        name = product.get("name", "")
        description = product.get("description_tr", "")
        full_text = f"{name} {description}"

        if eco_intent:
            # Sustainability-focused query: use hybrid (keywords + LLM)
            keyword_match = has_eco_keywords(description)
            llm_match = classify_eco_llm(description, llm_client)

            keyword_flag = 1 if keyword_match else 0
            llm_flag = 1 if llm_match else 0
            priority_score = keyword_flag * 2 + llm_flag

            # Only include products that look sustainable by at least one signal
            if priority_score == 0:
                continue
        else:
            # General query: simple keyword relevance
            relevance = score_text_relevance(tokens, full_text)
            if relevance == 0:
                continue
            priority_score = relevance

        ranked.append(
            {
                "product": product,
                "priority_score": priority_score,
            }
        )

    # Sort descending by priority_score
    ranked.sort(key=lambda r: r["priority_score"], reverse=True)
    return [r["product"] for r in ranked]


# =====================
# DATA LOADING
# =====================

@st.cache_data
def load_products() -> List[Dict[str, Any]]:
    """
    Expects a products.json file in the same folder as app.py.
    """
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)


# =====================
# STREAMLIT UI
# =====================

def main():
    st.set_page_config(
        page_title="Eco Product Search Demo",
        layout="centered",
    )

    st.title("Eco Product Search Demo")
    st.caption("A demo showing how sustainability signals can be inferred from product descriptions when structured eco-friendly attributes are missing from the catalog.")

    products = load_products()
    llm_client = DummyLLMClient()

    # Search input (no form, so no default Streamlit form hint)
    query = st.text_input(
        "Search product",
        placeholder="E.g.: eco friendly",
        key="search_query",
        on_change=_trigger_search,  # Enter in the box triggers this
    )

    # Search button directly below input
    search_clicked = st.button("Search")

    if search_clicked or st.session_state["run_search"]:
        st.session_state["run_search"] = False

    # Override Streamlit input styles so only a green border is shown
    st.markdown(
    """
    <style>
    /* Base border for the search input */
    div[data-testid="stTextInput"] input {
        border: 1px solid #00aa00 !important;
        box-shadow: none !important;
        outline: none !important;
    }
    /* Focus state: keep only green border and green focus ring */
    div[data-testid="stTextInput"] input:focus {
        border: 1px solid #00aa00 !important;
        box-shadow: 0 0 0 1px #00aa00 !important;
        outline: none !important;
    }
    /* Some Streamlit themes wrap the input; ensure wrapper border is also green */
    div[data-testid="stTextInput"] > div {
        border: 1px solid #00aa00 !important;
        box-shadow: none !important;
    }
    div[data-testid="stTextInput"] > div:focus-within {
        border: 1px solid #00aa00 !important;
        box-shadow: 0 0 0 1px #00aa00 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
    )

    # Override default Streamlit helper text so ONLY "Press Enter to search" is shown
    st.markdown(
    """
    <style>
    /* Make the text input container positionable */
    div[data-testid="stTextInput"] {
        position: relative;
    }
    /* Our custom helper text */
    div[data-testid="stTextInput"]::after {
        content: "Press Enter to search";
        position: absolute;
        right: 0.75rem;
        bottom: -1.1rem;
        font-size: 0.7rem;
        color: #888888;
        pointer-events: none;
    }
    </style>
    <script>
    // Remove Streamlit's default "Press Enter to submit form" helper text
    const removeDefaultHelper = () => {
      const candidates = document.querySelectorAll('span, div, small');
      candidates.forEach(el => {
        if (el.innerText && el.innerText.trim() === "Press Enter to submit form") {
          el.style.display = "none";
        }
      });
    };
    // Run once now
    window.addEventListener('load', removeDefaultHelper);
    // Also observe DOM changes in case Streamlit re-renders
    const observer = new MutationObserver(removeDefaultHelper);
    observer.observe(document.body, { childList: true, subtree: true });
    </script>
    """,
    unsafe_allow_html=True,
    )

    # Example helper block (directly under search input & button)
    st.markdown(
        "**Try example searches:**  \n"
        "- çevre dostu  \n"
        "- sürdürülebilir  \n"
        "- organik"
        "- eco friendly products  \n"
        "- sustainable furniture  \n"
    )

    if query.strip():
        with st.spinner("Analyzing products..."):
            results = run_search(products, query, llm_client)

        st.markdown("---")

        if not results:
            st.write("No results found.")

        for product in results:
            name = product.get("name", "")
            pid = product.get("id", "")
            price = product.get("price", 0.0)
            description = product.get("description_tr", "")

            st.markdown(f"### {name}")
            st.write(f"ID: {pid}")
            st.write(f"Price: {price:.2f} ₺")
            st.write(f"Description: {description}")
            st.markdown("---")


if __name__ == "__main__":
    main()