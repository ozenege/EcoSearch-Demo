import json
import re
from typing import List, Dict, Any, Tuple

import streamlit as st


# =====================
# BASIC TEXT UTILITIES
# =====================

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\sğüşiöç]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return normalize(text).split(" ")


# =====================
# INTENT DETECTION
# =====================

ECO_PHRASES = [
    "çevre dostu",
    "doğa dostu",
    "yeşil ürün",
]

ECO_TOKENS = [
    "eko",
    "ekolojik",
    "sürdürülebilir",
    "organik",
]


def detect_eco_intent(raw_query: str) -> Dict[str, Any]:
    """
    Simple deterministic intent detection.
    Returns a small dict used internally; not exposed in UI.
    """
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
# KEYWORD-BASED ECO SCORING
# =============================

ECO_KEYWORDS_STRONG = [
    "geri dönüştürülmüş ahşap",
    "geri dönüştürülmüş",
    "organik boya",
    "organik pamuk",
    "organik keten",
    "sürdürülebilir kumaş",
]

ECO_KEYWORDS_WEAK = [
    "su bazlı boya",
    "düşük voc",
    "doğa dostu",
    "yeşil ürün",
    "çevre dostu",
]

ECO_STRONG_WEIGHT = 2
ECO_WEAK_WEIGHT = 1


def score_text_relevance(query_tokens: List[str], text: str) -> int:
    norm = normalize(text)
    text_tokens = set(norm.split(" "))
    return sum(1 for t in query_tokens if t in text_tokens)


def score_eco_in_description(description: str) -> Tuple[int, List[str]]:
    desc_norm = normalize(description)
    eco_score = 0
    matches: List[str] = []

    for phrase in ECO_KEYWORDS_STRONG:
        if phrase in desc_norm:
            eco_score += ECO_STRONG_WEIGHT
            matches.append(phrase)

    for phrase in ECO_KEYWORDS_WEAK:
        if phrase in desc_norm:
            eco_score += ECO_WEAK_WEIGHT
            matches.append(phrase)

    return eco_score, matches


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
    For the MVP, we reuse eco keyword logic to simulate the LLM.
    Replace `.complete` with a real API call when integrating a provider.
    """

    def complete(self, prompt: str) -> str:
        desc = prompt.split("Description:", 1)[-1]
        eco_score, _ = score_eco_in_description(desc)
        return "YES" if eco_score > 0 else "NO"


def classify_eco_llm(description: str, llm_client: DummyLLMClient) -> bool:
    prompt = build_llm_prompt(description)
    raw = llm_client.complete(prompt).strip().upper()
    return raw == "YES"


# =============================
# HYBRID SEARCH LOGIC
# =============================

def keyword_search(products: List[Dict[str, Any]], parsed_query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Base keyword search and sustainability filtering.
    Returns a list of internal result dicts with scores used for ranking only.
    """
    results: List[Dict[str, Any]] = []
    tokens = parsed_query["tokens"]
    eco_intent = parsed_query["eco_intent"]

    for product in products:
        name = product.get("name", "")
        description = product.get("description_tr", "")
        combined = f"{name} {description}"

        if eco_intent:
            eco_score, _ = score_eco_in_description(description)
            if eco_score == 0:
                # User is asking for eco-friendly; description has no eco signals
                continue
            text_score = score_text_relevance(tokens, combined)
            final_score = eco_score * 10 + text_score
        else:
            text_score = score_text_relevance(tokens, combined)
            if text_score == 0:
                continue
            eco_score = 0
            final_score = float(text_score)

        results.append(
            {
                "product": product,
                "eco_score": eco_score,
                "text_score": text_score,
                "final_score": final_score,
                "llm_eco": None,
            }
        )

    results.sort(key=lambda r: r["final_score"], reverse=True)
    return results


def apply_hybrid_llm(
    results: List[Dict[str, Any]],
    llm_client: DummyLLMClient,
    max_llm_calls: int = 5,
) -> List[Dict[str, Any]]:
    """
    Hybrid behavior:
    - We already have an eco-filtered set from keywords when eco_intent is true.
    - Use LLM to validate/adjust top N results.
    - Scores are internal; UI only sees the ranked list of products.
    """
    top = results[:max_llm_calls]

    for res in top:
        desc = res["product"].get("description_tr", "")
        llm_flag = classify_eco_llm(desc, llm_client)
        res["llm_eco"] = llm_flag

        # Simple score adjustment:
        if llm_flag:
            res["final_score"] *= 1.1
        else:
            res["final_score"] *= 0.7

    results.sort(key=lambda r: r["final_score"], reverse=True)
    return results


def hybrid_search(
    products: List[Dict[str, Any]],
    raw_query: str,
    llm_client: DummyLLMClient,
) -> List[Dict[str, Any]]:
    """
    Full hybrid pipeline:
    1) Detect intent.
    2) Keyword-based search and eco filtering.
    3) If eco intent, use LLM to refine ranking.
    Returns a list of product dicts (no scores exposed to UI).
    """
    parsed = detect_eco_intent(raw_query)
    results = keyword_search(products, parsed)

    if parsed["eco_intent"] and results:
        results = apply_hybrid_llm(results, llm_client)

    # Map to plain product list for UI
    return [r["product"] for r in results]


# =====================
# DATA LOADING
# =====================

@st.cache_data
def load_products() -> List[Dict[str, Any]]:
    """
    Expects products.json (10-item catalog) in the same folder as app.py.
    """
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)


# =====================
# STREAMLIT UI
# =====================

def main():
    st.set_page_config(
        page_title="Furniture Search (Sustainability-aware)",
        layout="centered",
    )

    st.title("Furniture Search Prototype")
    st.caption("This is a prototype for a new furniture search engine feature.")

    products = load_products()
    query = st.text_input(
        "Search furniture",
        #placeholder="Örn: çevre dostu ahşap masa",
    )

    if st.button("Search") and query.strip():
        llm_client = DummyLLMClient()
        matched_products = hybrid_search(
            products=products,
            raw_query=query,
            llm_client=llm_client,
        )

        st.subheader("Results")

        if not matched_products:
            st.info("No products found matching your search criteria.")
            return

        for p in matched_products:
            st.markdown(f"### {p.get('name', '')}")
            st.caption(
                f"ID: {p.get('id', '')} · "
                f"Category: {p.get('category', '')} · "
                f"Price: {p.get('price', '')}"
            )
            st.write(p.get("description_tr", ""))
            st.markdown("---")


if __name__ == "__main__":
    main()