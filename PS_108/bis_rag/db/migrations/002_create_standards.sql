-- Migration 002: standards (core table)
--
-- Field mapping: raw scraper → DB column
--
--   standard_number (top-level)          → standard_number  [canonical; basic_details.std_number same]
--   title (top-level)                    → title            [canonical; basic_details.title_full in raw_data]
--   date_of_publish                      → date_of_publish
--   type_of_standard (top-level)         → type_of_standard [same in basic_details]
--   degree_of_equivalence (top-level)    → degree_of_equivalence [same in basic_details]
--   detail_url / lifecycle_path / current_status → direct columns
--   basic_details.department             → department
--   basic_details.committee              → committee
--   basic_details.superseding_is         → superseding_is_raw (FK resolved later)
--   basic_details.no_of_revisions        → no_of_revisions (int; "New Standard" → 0)
--   basic_details.no_of_amendments       → no_of_amendments (int; "No amendment issued" → 0)
--   basic_details.language               → language
--   basic_details.reaffirmation_year     → reaffirmation_year TEXT ("Jan, 2022" format)
--   basic_details.member_secretary       → member_secretary
--   classification_details.group         → std_group ("group" is SQL reserved word)
--   classification_details.sub_group     → sub_group
--   classification_details.sub_sub_group → sub_sub_group
--   classification_details.certification → certification
--   classification_details.relevant_ministries → relevant_ministries
--   classification_details.sdg           → sdg
--   classification_details.short_common_man_title → short_common_man_title
--   classification_details.ics_code      → ics_code
--   classification_details.equivalent_standards → equivalent_standards (raw text)
--   scraped_at                           → scraped_at
--   (entire raw record)                  → raw_data JSONB

CREATE TABLE IF NOT EXISTS standards (
    id                      BIGSERIAL PRIMARY KEY,
    standard_number         TEXT NOT NULL,
    standard_number_base    TEXT,
    title                   TEXT,
    date_of_publish         DATE,
    type_of_standard        TEXT,
    degree_of_equivalence   TEXT,
    current_status          TEXT,
    lifecycle_path          TEXT,
    detail_url              TEXT,
    department              TEXT,
    committee               TEXT,
    language                TEXT,
    reaffirmation_year      TEXT,      -- stored as text: values like "Jan, 2022"
    member_secretary        TEXT,
    no_of_revisions         INTEGER,
    no_of_amendments        INTEGER,
    superseding_is_raw      TEXT,
    superseding_standard_id BIGINT REFERENCES standards(id) ON DELETE SET NULL,
    std_group               TEXT,      -- renamed from "group" (SQL reserved word)
    sub_group               TEXT,
    sub_sub_group           TEXT,
    certification           TEXT,
    relevant_ministries     TEXT,
    sdg                     TEXT,
    short_common_man_title  TEXT,
    ics_code                TEXT,
    equivalent_standards    TEXT,
    scraped_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_data                JSONB NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX uq_standards_number      ON standards(standard_number);
CREATE INDEX idx_standards_number_base       ON standards(standard_number_base);
CREATE INDEX idx_standards_department        ON standards(department);
CREATE INDEX idx_standards_committee         ON standards(committee);
CREATE INDEX idx_standards_status            ON standards(current_status);
CREATE INDEX idx_standards_type              ON standards(type_of_standard);
CREATE INDEX idx_standards_ics_code          ON standards(ics_code);
CREATE INDEX idx_standards_certification     ON standards(certification);
CREATE INDEX idx_standards_scraped_at        ON standards(scraped_at);
CREATE INDEX idx_standards_title_gin         ON standards USING gin (to_tsvector('english', coalesce(title, '')));
