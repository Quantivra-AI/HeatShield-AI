
import json
import re
from pathlib import Path
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = BACKEND_DIR / "data" / "biotwin" / "reports"
GLOBAL_KNOWLEDGE_DIR = BACKEND_DIR / "data" / "knowledge" / "processed"

DOCUMENTS = []

# Controlled expansion terms. These improve recall without replacing
# the original user question.
QUERY_EXPANSIONS = {
    "monitor": (
        "occupational health surveillance medical check-ups "
        "heart rate recovery heart rate core body temperature "
        "hydration body water loss workplace monitoring"
    ),
    "surveillance": (
        "worker health monitoring environmental monitoring "
        "occupational health services medical examination"
    ),
    "workplace risks": (
        "heat stress heat-related illness occupational injuries "
        "heat exhaustion heatstroke dehydration kidney disorders"
    ),
    "excessive heat": (
        "occupational heat exposure thermal stress worker safety "
        "health impacts heat-related injuries"
    ),
    "acclimation": (
        "heat acclimatization physiological adaptation "
        "core temperature sweat rate thermoregulation"
    ),
    "hydration": (
        "fluid intake water loss dehydration sweat production "
        "body mass change"
    ),
    "work rest": (
        "rest breaks recovery periods work-rest schedules "
        "workload exposure reduction"
    ),
    "wbgt": (
        "wet bulb globe temperature occupational heat exposure "
        "environmental heat assessment"
    ),
    "ppe": (
        "personal protective equipment clothing insulation "
        "impermeable clothing heat stress"
    ),
    "heat-related illness": (
        "heat illness heat cramps heat exhaustion heat stroke heat rash "
        "early symptoms recognition first aid emergency response"
    ),
    "heat related illness": (
        "heat illness heat cramps heat exhaustion heat stroke heat rash "
        "early symptoms recognition first aid emergency response"
    ),
    "heat exhaustion": (
        "heat exhaustion symptoms signs first aid cooling oral fluids "
        "medical care recovery"
    ),
    "heat stroke": (
        "exertional heat stroke altered mental status confusion unconsciousness "
        "rapid whole body cooling cold water immersion emergency transport"
    ),
    "first aid": (
        "first-aid treatment immediate response cooling fluids shade "
        "medical evaluation emergency medical services"
    ),
    "emergency preparedness": (
        "emergency plan early recognition first-line supervisors workers "
        "immediate aggressive cooling emergency transport healthcare facility"
    ),
    "buddy system": (
        "mutual monitoring coworkers periodic observation early signs symptoms "
        "heat-related illness training"
    ),
    "worker education": (
        "heat stress training program worker supervisor symptom recognition "
        "prevention acclimatization reporting emergency procedures"
    ),
    "return to work": (
        "return-to-work considerations days away from heat exposure "
        "reduced work assignment recovery after heat illness"
    ),
    "clinical treatment": (
        "management health outcomes workplace heat stress section 4.4 "
        "heat exhaustion heat stroke cooling oral fluids medical care"
    ),
    "cardiovascular": (
        "cardiovascular disease heart disease hypertension cardiac strain "
        "heart rate blood pressure heat exposure chronic conditions"
    ),
    "heart disease": (
        "cardiovascular disease cardiac conditions hypertension heart rate "
        "blood pressure heat exposure clinical risk factors"
    ),
    "kidney": (
        "renal disease chronic kidney disease kidney function acute kidney injury "
        "dehydration heat exposure renal impairment"
    ),
    "renal": (
        "kidney disease chronic kidney disease renal function acute kidney injury "
        "dehydration heat exposure"
    ),
    "respiratory": (
        "asthma chronic respiratory disease pulmonary conditions air quality "
        "heat health clinical guidance"
    ),
    "asthma": (
        "asthma respiratory disease heat health clinical guidance "
        "air quality heat exposure"
    ),
    "diabetes": (
        "diabetes metabolic disease glucose regulation insulin heat medications "
        "dehydration chronic conditions"
    ),
    "metabolic": (
        "diabetes metabolic conditions glucose regulation insulin medications "
        "heat exposure clinical risk factors"
    ),
    "neurological": (
        "neurological disease neurologic conditions cognitive function "
        "heat illness nervous system chronic conditions"
    ),
    "chronic disease": (
        "pre-existing chronic conditions cardiovascular kidney renal respiratory "
        "asthma diabetes metabolic neurological heat vulnerability clinical guidance"
    ),
    "long-term effects": (
        "long-term health outcomes chronic disease development progression "
        "longitudinal cohort follow-up heat exposure evidence limitations"
    ),
    "disease progression": (
        "chronic disease progression longitudinal evidence cohort follow-up "
        "heat exposure disease incidence causality"
    ),
}


def add_document(source, title, content, **metadata):
    content = str(content).strip()

    if content:
        DOCUMENTS.append({
            "source": source,
            "title": title,
            "content": content,
            **metadata,
        })


def _load_biotwin_research():
    ml_path = REPORT_DIR / "ML_EXPERIMENT_FINDINGS.md"

    if ml_path.exists():
        add_document(
            "ML_EXPERIMENT_FINDINGS.md",
            "PROSPIE ML experiment findings",
            ml_path.read_text(encoding="utf-8"),
            knowledge_domain="biotwin_research",
            authority_type="research_analysis",
        )

    physiological_path = REPORT_DIR / "physiological_paired_analysis.json"

    if physiological_path.exists():
        data = json.loads(
            physiological_path.read_text(encoding="utf-8")
        )

        add_document(
            "physiological_paired_analysis.json",
            "Human heat acclimation study overview",
            (
                f"Dataset: {data.get('dataset')}. "
                f"Total records: {data.get('total_records')}. "
                f"Participants: {data.get('total_participants')}. "
                f"Complete paired participants: "
                f"{data.get('complete_paired_participants')}. "
                f"Sample size note: {data.get('sample_size_note')}"
            ),
            knowledge_domain="biotwin_research",
            authority_type="research_analysis",
        )

        for result in data.get("results", []):
            if result.get("exploratory_significance_bh05"):
                variable = result.get("variable", "")

                labels = {
                    "normothermic_tcore_initial__c": (
                        "Core body temperature, "
                        "normothermic heat acclimation"
                    ),
                    "normothermic_mean_tbody_initial__c": (
                        "Mean body temperature, "
                        "normothermic heat acclimation"
                    ),
                }

                readable_name = labels.get(variable, variable)

                content = (
                    f"Human heat acclimation research. "
                    f"Finding: {readable_name}. "
                    f"Variable: {variable}. "
                    f"Participants: {result.get('n_pairs')}. "
                    f"Before acclimation mean: {result.get('pre_mean')}. "
                    f"After acclimation mean: {result.get('post_mean')}. "
                    f"Mean change: "
                    f"{result.get('mean_change_post_minus_pre')}. "
                    f"95% CI: "
                    f"{result.get('mean_change_ci_95_lower')} to "
                    f"{result.get('mean_change_ci_95_upper')}. "
                    f"Statistical test: {result.get('test_used')}. "
                    f"Adjusted p-value: "
                    f"{result.get('p_value_adjusted_bh')}."
                )

                add_document(
                    "physiological_paired_analysis.json",
                    f"Heat acclimation: {readable_name}",
                    content,
                    knowledge_domain="biotwin_research",
                    authority_type="research_analysis",
                )

    prospie_path = REPORT_DIR / "prospie_research_report.json"

    if prospie_path.exists():
        data = json.loads(
            prospie_path.read_text(encoding="utf-8")
        )

        add_document(
            "prospie_research_report.json",
            "PROSPIE research summary",
            json.dumps(data, ensure_ascii=False, indent=2),
            knowledge_domain="biotwin_research",
            authority_type="research_analysis",
        )

    quality_path = REPORT_DIR / "data_quality_report.json"

    if quality_path.exists():
        data = json.loads(
            quality_path.read_text(encoding="utf-8")
        )

        add_document(
            "data_quality_report.json",
            "BioTwin dataset quality report",
            json.dumps(data, ensure_ascii=False, indent=2),
            knowledge_domain="biotwin_research",
            authority_type="dataset_quality_report",
        )


def _load_global_knowledge():
    if not GLOBAL_KNOWLEDGE_DIR.exists():
        return

    for jsonl_path in sorted(GLOBAL_KNOWLEDGE_DIR.glob("*.jsonl")):
        with jsonl_path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"Skipping invalid JSON: {jsonl_path.name}, "
                        f"line {line_number}"
                    )
                    continue

                content = str(item.get("content", "")).strip()

                if len(content) < 80:
                    continue

                source_id = item.get(
                    "source_id",
                    jsonl_path.stem,
                )

                add_document(
                    source=source_id,
                    title=item.get("title", jsonl_path.stem),
                    content=content,
                    knowledge_domain="global_knowledge",
                    organization=item.get("organization"),
                    document_type=item.get("document_type"),
                    domains=item.get("domains", []),
                    jurisdiction=item.get("jurisdiction"),
                    publication_date=item.get("publication_date"),
                    authority_type=item.get("authority_type"),
                    evidence_grade=item.get("evidence_grade"),
                    reuse_status=item.get("reuse_status"),
                    source_url=item.get("source_url"),
                    source_file=item.get("source_file"),
                    source_sha256=item.get("source_sha256"),
                    page_start=item.get("page_start"),
                    page_end=item.get("page_end"),
                    chunk_index=item.get("chunk_index"),
                )


def load_knowledge_base():
    global DOCUMENTS
    DOCUMENTS = []

    _load_biotwin_research()
    _load_global_knowledge()

    return DOCUMENTS


def _looks_like_toc(text: str) -> bool:
    import re

    normalized = re.sub(r"\s+", " ", text).strip().lower()

    if "table of contents" in normalized:
        return True

    # Numbered section headings
    section_matches = re.findall(
        r"\b\d+(?:\.\d+){0,3}\s+[a-z][^.!?]{2,100}?\s+\d{1,3}\b",
        normalized,
    )

    # Major navigation headings
    navigation_matches = re.findall(
        r"\b(?:part\s+[a-z]|annex\s+[ivx\d]+|references|"
        r"acknowledgements|list of abbreviations)\b",
        normalized,
    )

    # Heading followed by page number is a strong TOC pattern
    navigation_page_pairs = re.findall(
        r"\b(?:references|annex\s+[ivx\d]+|part\s+[a-z])"
        r"[^.!?]{0,100}?\b\d{1,3}\b",
        normalized,
    )

    # Continuation pages may not contain the TOC title.
    if len(section_matches) >= 3 and (
        len(navigation_matches) >= 2
        or len(navigation_page_pairs) >= 2
    ):
        return True

    return False


def _looks_like_reference_list(content):
    """Exclude chunks dominated by bibliography entries."""
    text = content.lower()

    years = re.findall(r"\b(?:19|20)\d{2}\b", text)
    urls = re.findall(r"https?://|doi\.org/", text)
    author_patterns = re.findall(
        r"\b[A-Z][a-z]+,\s+[A-Z]",
        content,
    )

    sentences = re.findall(r"[.!?](?:\s|$)", content)

    return (
        len(years) >= 8
        and len(author_patterns) >= 3
        and len(urls) >= 2
        and len(sentences) <= 3
    )


def _is_retrievable(document):
    content = document["content"]

    if len(content) < 120:
        return False

    if document.get("knowledge_domain") == "global_knowledge":
        if _looks_like_toc(content):
            return False

        if _looks_like_reference_list(content):
            return False

    return True


def _expand_query(question):
    expanded_terms = []

    for phrase, expansion in QUERY_EXPANSIONS.items():
        if phrase in question.lower():
            expanded_terms.append(expansion)

    return " ".join([question, *expanded_terms])


def retrieve_evidence(question, top_k=8):
    documents = [
        document
        for document in load_knowledge_base()
        if _is_retrievable(document)
    ]

    if not documents:
        return []

    corpus = [
        f"{doc['title']} {doc['source']} "
        f"{doc.get('organization', '')} "
        f"{' '.join(doc.get('domains', []))} "
        f"{doc['content']}"
        for doc in documents
    ]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )

    try:
        matrix = vectorizer.fit_transform(corpus)

        original_vector = vectorizer.transform([question])
        expanded_vector = vectorizer.transform([
            _expand_query(question)
        ])

        original_scores = cosine_similarity(
            original_vector,
            matrix,
        ).flatten()

        expanded_scores = cosine_similarity(
            expanded_vector,
            matrix,
        ).flatten()

    except ValueError:
        return []

    # Keep the original wording influential while improving recall
    # for domain-specific terminology.
    combined_scores = (
        0.40 * original_scores
        + 0.60 * expanded_scores
    )

    # Targeted phrase boosts improve recall for clinically important passages
    # without allowing a source label or broad topic match to dominate retrieval.
    question_lower = question.lower()
    phrase_boosts = {
        "heat-related illness": ("heat exhaustion", "heat stroke", "first aid"),
        "heat related illness": ("heat exhaustion", "heat stroke", "first aid"),
        "emergency preparedness": ("emergency plan", "aggressive cooling", "transport"),
        "buddy system": ("buddy system", "periodic intervals", "coworker"),
        "return to work": ("return to work", "return-to-work", "full activity"),
        "heat exhaustion": ("heat exhaustion", "oral fluids", "cool environment"),
        "heat stroke": ("heat stroke", "altered mental status", "cooling"),
        "cardiovascular": ("cardiovascular disease", "ischemic heart disease", "heart rate", "hypertension"),
        "heart disease": ("cardiovascular disease", "ischemic heart disease", "heat-related illness"),
        "chronic kidney": ("chronic kidney disease", "CKD", "renal function", "heat stress"),
        "kidney disease": ("chronic kidney disease", "CKD", "renal function", "heat stress"),
        "respiratory": ("asthma", "respiratory disease", "shortness of breath"),
        "diabetes": ("diabetes", "insulin", "medication management", "heat"),
        "neurological": ("neurological dysfunction", "neurological disease", "heat strain"),
        "long-term disease": ("long-term health consequences", "chronic kidney disease", "chronic disorder"),
        "disease progression": ("long-term effects", "chronic disorder", "research needs"),
    }
    for trigger, terms in phrase_boosts.items():
        if trigger in question_lower:
            for index, document in enumerate(documents):
                content_lower = document["content"].lower()
                title_lower = document["title"].lower()
                hits = sum(term in content_lower or term in title_lower for term in terms)
                if hits:
                    combined_scores[index] += min(0.025 * hits, 0.06)

    ranked = combined_scores.argsort()[::-1]

    results = []

    for index in ranked:
        score = float(combined_scores[index])

        if score < 0.035:
            continue

        results.append({
            **documents[index],
            "relevance_score": round(score, 4),
            "original_query_score": round(
                float(original_scores[index]), 4
            ),
            "expanded_query_score": round(
                float(expanded_scores[index]), 4
            ),
        })

        if len(results) >= top_k:
            break

    return results
