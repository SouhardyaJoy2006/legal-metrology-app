"""
Glue layer between the two prototype scripts (Data_Extractor/classify_product.py
and Label_Scanner/extractor.py) and the Flask app.

- classify_category(): CLIP zero-shot classification of the PRODUCT photo
  into edible / electronic / cosmetic.
- extract_label_data(): Gemini vision extraction of the LABEL photo into the
  mandatory Legal Metrology declaration fields.
- run_compliance_check(): ties the two together with standards.py to produce
  a single report dict the templates can render.

Both AI calls are wrapped so a missing dependency (no GPU/torch) or a missing
GEMINI_API_KEY doesn't crash the whole app — the report will just say the
step failed, instead of raising a 500.
"""

import json
import os

from standards import BOOLEAN_FIELDS, FIELD_INFO, get_standard

# ---------------------------------------------------------------------------
# CLIP product-category classifier
# (adapted from Data_Extractor/classify_product.py, wrapped for reuse instead
# of being a one-shot CLI script; the model loads once, lazily, on first use)
# ---------------------------------------------------------------------------

_clip_model = None
_clip_preprocess = None
_clip_device = "cpu"
_clip_category_embeddings = None

CATEGORY_PROMPTS = {
    "edible": [
        "a photo of a food product package",
        "a packet of biscuits or snacks",
        "a food item wrapped in plastic packaging",
        "a bottle of cooking oil or beverage",
        "a bag of grains, rice, or pulses",
    ],
    "electronic": [
        "a photo of an electronic device or gadget",
        "a packaged electronic appliance",
        "a phone charger or cable in its box",
        "an electronic device with a screen or buttons",
        "a battery or electronic accessory package",
    ],
    "cosmetic": [
        "a photo of a cosmetic or personal care product",
        "a tube of cream, lotion, or toothpaste",
        "a bottle of shampoo or skincare product",
        "a soap bar or bathing product",
        "a makeup or beauty product package",
    ],
}


def _load_clip():
    """Lazily import torch/clip and load the model once per process."""
    global _clip_model, _clip_preprocess, _clip_device, _clip_category_embeddings

    if _clip_model is not None:
        return

    import torch
    import clip

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"
    _clip_model, _clip_preprocess = clip.load("ViT-B/32", device=_clip_device)

    category_embeddings = {}
    with torch.no_grad():
        for category, prompts in CATEGORY_PROMPTS.items():
            tokens = clip.tokenize(prompts).to(_clip_device)
            features = _clip_model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
            category_embeddings[category] = features.mean(dim=0)
    _clip_category_embeddings = category_embeddings


def classify_category(image_path: str) -> dict:
    """
    Returns:
        {
          "ok": True,
          "predicted_category": "edible",
          "confidence": {"edible": 0.81, "cosmetic": 0.12, "electronic": 0.07},
        }
    or, on failure:
        {"ok": False, "error": "<message>"}

    Tries CLIP first (local/full-feature environments). If CLIP/torch isn't
    available (e.g. on Vercel, where they're excluded from requirements.txt
    for deployment size reasons) or otherwise fails, falls back to a Gemini
    vision-based classification so category prediction still works.
    """
    try:
        import torch
        from PIL import Image

        _load_clip()

        image = _clip_preprocess(Image.open(image_path).convert("RGB"))
        image = image.unsqueeze(0).to(_clip_device)

        with torch.no_grad():
            image_features = _clip_model.encode_image(image)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        scores = {}
        for category, text_feat in _clip_category_embeddings.items():
            similarity = (image_features @ text_feat.unsqueeze(1)).item()
            scores[category] = similarity

        sims = torch.tensor(list(scores.values()))
        probs = torch.softmax(sims * 100, dim=0)  # sharpen CLIP's cosine sims
        confidence = dict(zip(scores.keys(), probs.tolist()))
        predicted = max(confidence, key=confidence.get)

        return {"ok": True, "predicted_category": predicted, "confidence": confidence, "method": "clip"}

    except Exception as clip_exc:  # missing torch/CLIP weights, bad image, etc.
        return _classify_category_via_gemini(image_path, clip_error=str(clip_exc))


def _classify_category_via_gemini(image_path: str, clip_error: str = "") -> dict:
    """Fallback classifier used when CLIP isn't available (e.g. on Vercel)."""
    try:
        import PIL.Image

        client = _load_gemini_client()
        img = PIL.Image.open(image_path)

        prompt = (
            "Classify this product photo into exactly one of these three "
            'categories: "edible", "electronic", "cosmetic". Return ONLY '
            "valid JSON (no markdown, no extra text) in this exact shape: "
            '{"predicted_category": "edible", "confidence": '
            '{"edible": 0.8, "electronic": 0.1, "cosmetic": 0.1}}'
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=[prompt, img]
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.replace("json\n", "", 1).strip()

        data = json.loads(raw_text)
        return {
            "ok": True,
            "predicted_category": data["predicted_category"],
            "confidence": data.get("confidence", {}),
            "method": "gemini_fallback",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Category classification failed (CLIP unavailable: {clip_error}; Gemini fallback also failed: {exc})",
        }


# ---------------------------------------------------------------------------
# Gemini label declaration extractor
# (adapted from Label_Scanner/extractor.py, minus the CSV side effect —
# the Flask app persists results in the database instead)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """
Analyze this packaged commodity label for compliance under the Legal Metrology
(Packaged Commodities) Rules & Cosmetics Rules (P34).

Extract and evaluate the following declarations. Return ONLY valid JSON
(no markdown, no code fences, no extra text) with exactly these keys:

{
  "product_name": "generic/common name of the commodity",
  "manufacturer_details": "name, complete address, PIN code of manufacturer/packer/importer",
  "net_quantity": "exact net weight/volume in standard units (g, kg, ml, L, N)",
  "mfg_pack_date": "month and year of manufacture/packing/import , add date of import if anything else is not mentioned",
  "expiry_date": "expiry or best-before date if applicable, else empty string",
  "mrp": "Maximum Retail Price inclusive of all taxes, exact text as printed",
  "consumer_care_details": "phone number, email, address for consumer complaints",
  "spacing_compliant": 0 or 1,
  "language_visibility_compliant": 0 or 1,
  "placement_compliant": 0 or 1,
  "dimensions_declared": 0 or 1,
  "color_contrast_compliant": 0 or 1
}

Rules for the boolean fields:
- spacing_compliant: net quantity has free space around it (>= numeral height above/below, >= 2x numeral height left/right)
- language_visibility_compliant: legible, prominent, in English or Hindi (Devnagari)
- placement_compliant: all required declarations appear on the principal display panel
- dimensions_declared: 1 only if dimensions are relevant for this product type (e.g. bedsheets, napkins) AND present; else 1 if not applicable
- color_contrast_compliant: net quantity and MRP numerals contrast clearly against background

If a field cannot be determined from the image, use an empty string "" for text fields
or 0 for boolean fields — never omit a key.
"""
_gemini_client = None


def _load_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set in the environment.")

    from google import genai

    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def extract_label_data(image_path: str) -> dict:
    """
    Returns:
        {"ok": True, "data": {...the FIELDNAMES from extractor.py...}}
    or:
        {"ok": False, "error": "<message>"}
    """
    try:
        import PIL.Image

        client = _load_gemini_client()
        img = PIL.Image.open(image_path)

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=[EXTRACTION_PROMPT, img]
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.replace("json\n", "", 1).strip()

        data = json.loads(raw_text)
        return {"ok": True, "data": data}

    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Model did not return valid JSON: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"Label extraction failed: {exc}"}


# ---------------------------------------------------------------------------
# Matching engine: extracted label data + category -> pass/fail report
# ---------------------------------------------------------------------------

def _field_is_present(field: str, value) -> bool:
    if field in BOOLEAN_FIELDS:
        return bool(value) and str(value) not in ("0", "0.0", "False", "")
    return value is not None and str(value).strip() != ""


def match_against_standards(category: str, extracted_data: dict) -> dict:
    """
    Compares extracted_data against the required fields for `category` and
    returns a structured, template-friendly report:

    {
      "category": "edible",
      "display_name": "Food & Beverage (Edible)",
      "notes": [...],
      "fields": [
        {"field": "mrp", "label": "...", "rule": "...", "required": True,
         "value": "Rs. 45.00", "compliant": True},
        ...
      ],
      "total_required": 9,
      "total_compliant": 7,
      "overall_status": "Non-Compliant",  # or "Compliant"
    }
    """
    standard = get_standard(category)
    required_fields = standard["required_fields"]

    rows = []
    for field in required_fields:
        value = extracted_data.get(field, "")
        info = FIELD_INFO.get(field, {"label": field, "rule": ""})
        compliant = _field_is_present(field, value)
        rows.append({
            "field": field,
            "label": info["label"],
            "rule": info["rule"],
            "required": True,
            "value": value,
            "compliant": compliant,
        })

    total_required = len(rows)
    total_compliant = sum(1 for r in rows if r["compliant"])
    overall_status = "Compliant" if total_compliant == total_required else "Non-Compliant"

    return {
        "category": category,
        "display_name": standard["display_name"],
        "notes": standard.get("notes", []),
        "fields": rows,
        "total_required": total_required,
        "total_compliant": total_compliant,
        "overall_status": overall_status,
    }


def run_compliance_check(product_image_path: str, label_image_path: str) -> dict:
    """
    Full pipeline used by the Flask route:
      1. classify the product photo -> category
      2. extract declarations from the label photo
      3. fetch that category's standards and match extracted data against it

    Always returns a dict (never raises) so the route can persist a
    compliance_report / status regardless of partial failures.
    """
    classification = classify_category(product_image_path)
    extraction = extract_label_data(label_image_path)

    report = {
        "classification": classification,
        "extraction": extraction,
        "match": None,
    }

    if classification.get("ok") and extraction.get("ok"):
        category = classification["predicted_category"]
        report["match"] = match_against_standards(category, extraction["data"])
    elif extraction.get("ok"):
        # Classification failed but we still have label data — fall back to
        # matching against the full checklist rather than blocking entirely.
        report["match"] = match_against_standards("unknown", extraction["data"])

    return report
