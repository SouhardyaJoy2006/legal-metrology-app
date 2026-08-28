"""
Legal Metrology (Packaged Commodities) Rules, 2011 / Cosmetics Rules 2020 —
category-specific standards used to judge whether a set of extracted label
declarations is compliant.

The CLIP classifier (Data_Extractor/classify_product.py) only knows three
buckets: edible / electronic / cosmetic. We map those onto the richer set of
requirements each category actually carries under Legal Metrology, then use
this table to decide, field by field, whether a scan passes.
"""

# Fields that are ALWAYS mandatory on every packaged commodity regardless of
# category (Rule 6 of the Packaged Commodities Rules).
BASE_REQUIRED_FIELDS = [
    "product_name",
    "manufacturer_details",
    "net_quantity",
    "mfg_pack_date",
    "mrp",
    "consumer_care_details",
]

# Human-readable labels + short "why it matters" text, shown in the UI.
FIELD_INFO = {
    "product_name": {
        "label": "Generic / Common Name",
        "rule": "Rule 6(1)(a) — common or generic name of the commodity",
    },
    "manufacturer_details": {
        "label": "Manufacturer / Packer / Importer Details",
        "rule": "Rule 6(1)(b) — name & complete address incl. PIN code",
    },
    "net_quantity": {
        "label": "Net Quantity",
        "rule": "Rule 6(1)(c) — net weight/volume in standard units",
    },
    "mfg_pack_date": {
        "label": "Month & Year of Manufacture/Packing",
        "rule": "Rule 6(1)(e) — month and year of manufacture or packing",
    },
    "expiry_date": {
        "label": "Best-Before / Expiry Date",
        "rule": "Mandatory for perishables/cosmetics with a shelf life",
    },
    "mrp": {
        "label": "Maximum Retail Price (incl. all taxes)",
        "rule": "Rule 6(1)(f) — MRP inclusive of all taxes",
    },
    "consumer_care_details": {
        "label": "Consumer Care Contact",
        "rule": "Rule 6(1)(b) — contact for consumer complaints",
    },
    "spacing_compliant": {
        "label": "Net Quantity Spacing",
        "rule": "Rule 7 — clear space around the net-quantity declaration",
    },
    "language_visibility_compliant": {
        "label": "Language & Legibility",
        "rule": "Rule 8 — legible, in English or Hindi (Devnagari)",
    },
    "placement_compliant": {
        "label": "Principal Display Panel Placement",
        "rule": "Rule 6 — all declarations grouped on the principal display panel",
    },
    "dimensions_declared": {
        "label": "Dimensions (where applicable)",
        "rule": "Rule 9 — dimensions declared for items like linen, bedsheets",
    },
    "color_contrast_compliant": {
        "label": "Colour Contrast",
        "rule": "Rule 8 — numerals contrast clearly against the background",
    },
}

# Per-category rule set: which fields are required, and any category-specific
# notes surfaced in the report.
CATEGORY_STANDARDS = {
    "edible": {
        "display_name": "Food & Beverage (Edible)",
        "required_fields": BASE_REQUIRED_FIELDS + [
            "expiry_date",
            "spacing_compliant",
            "language_visibility_compliant",
            "placement_compliant",
            "color_contrast_compliant",
        ],
        "notes": [
            "Best-before/expiry date is mandatory for all food items.",
            "FSSAI license number should also appear on food packaging "
            "(not yet extracted by this prototype).",
        ],
    },
    "cosmetic": {
        "display_name": "Cosmetics & Personal Care",
        "required_fields": BASE_REQUIRED_FIELDS + [
            "expiry_date",
            "spacing_compliant",
            "language_visibility_compliant",
            "placement_compliant",
            "color_contrast_compliant",
        ],
        "notes": [
            "Cosmetics Rules 2020 require a 'period after opening' (PAO) or "
            "expiry date where applicable.",
            "Ingredient/INCI listing is required but not yet extracted by "
            "this prototype.",
        ],
    },
    "electronic": {
        "display_name": "Electronics & Appliances",
        "required_fields": BASE_REQUIRED_FIELDS + [
            "spacing_compliant",
            "language_visibility_compliant",
            "placement_compliant",
            "color_contrast_compliant",
        ],
        "notes": [
            "Expiry date is generally not applicable to electronics and is "
            "excluded from the required-field set for this category.",
            "BIS/ISI compliance marks are checked separately from Legal "
            "Metrology declarations.",
        ],
    },
}

# Boolean fields (already 0/1 from the extractor) vs free-text fields, so the
# matcher knows how to judge "present" / "compliant" differently.
BOOLEAN_FIELDS = {
    "spacing_compliant",
    "language_visibility_compliant",
    "placement_compliant",
    "dimensions_declared",
    "color_contrast_compliant",
}


def get_standard(category: str) -> dict:
    """Look up the rule set for a classifier category, case-insensitively.

    Falls back to the union of all fields if the category is unrecognized,
    so the report still renders something useful rather than crashing.
    """
    key = (category or "").strip().lower()
    if key in CATEGORY_STANDARDS:
        return CATEGORY_STANDARDS[key]

    all_fields = sorted({f for s in CATEGORY_STANDARDS.values() for f in s["required_fields"]})
    return {
        "display_name": category or "Unknown",
        "required_fields": all_fields,
        "notes": ["Category not recognized — showing the full field checklist."],
    }
