#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute and update description statistics, topic rankings, metric distributions, and fun facts.

Stores the resulting data in:
- description_topics
- description_metric_distributions
- description_fun_facts
"""

import argparse
import collections
import json
import math
import os
import re
import sqlite3
import sys

from create_db import DATABASE_PATH, ensure_schema

EXCLUDED_SUBJECT = "Diplomatervezés 2 (MSc)"


def open_db(path):
    if not os.path.exists(path) and os.path.exists("data/db/descriptions.sqlite"):
        path = "data/db/descriptions.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def extract_keywords_from_text(title, goal=""):
    """Heuristic keyword extractor when extract keywords are not yet populated."""
    text = f"{title or ''} {goal or ''}"
    words = re.findall(r"[A-Za-z0-9áéíóöőúüűÁÉÍÓÖŐÚÜŰ\-\+]{3,}", text)
    stopwords = {
        "alapu", "alapú", "esetén", "során", "való", "mint", "egy", "meg", "hogy",
        "nem", "mert", "rendszer", "rendszerek", "fejlesztése", "vizsgálata", "elemzése",
        "alkalmazása", "összehasonlító", "tervezése", "készítése", "megvalósítása",
        "modellezése", "optimalizálása", "kiértékelése", "támogató", "alapuló",
        "the", "and", "for", "with", "based", "system", "using", "from",
    }
    cleaned = []
    for w in words:
        wl = w.lower()
        if wl not in stopwords and len(w) >= 3:
            cleaned.append(w)
    return cleaned


def collect_keywords_and_theses(conn):
    """Collect keywords and titles of the latest version of each thesis (excluding Diplomatervezés 2)."""
    rows = conn.execute(
        """
        SELECT i.filename, i.neptun_code, i.title_hu, i.title_en,
               e.thesis_title, e.project_goal,
               e.keyword1, e.keyword2, e.keyword3, e.keyword4, e.keyword5
        FROM "import" AS i
        JOIN (
            SELECT neptun_code, MAX(version) AS version
            FROM "import"
            GROUP BY neptun_code
        ) AS latest ON latest.neptun_code = i.neptun_code AND latest.version = i.version
        LEFT JOIN "extract" AS e ON e.filename = i.filename
        WHERE (i.subject IS NULL OR TRIM(i.subject) != ?)
        ORDER BY i.filename
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchall()

    theses = []
    keyword_counts = collections.Counter()
    total_with_keywords = 0

    for r in rows:
        title = r["title_hu"] or r["title_en"] or r["thesis_title"] or ""
        kw_list = [r[f"keyword{idx}"] for idx in range(1, 6) if r[f"keyword{idx}"]]
        if kw_list:
            total_with_keywords += 1
            for kw in kw_list:
                keyword_counts[kw.strip()] += 1
        else:
            # Fallback keywords from title
            fallback_kws = extract_keywords_from_text(title, r["project_goal"])
            for kw in fallback_kws[:3]:
                keyword_counts[kw] += 1
            kw_list = fallback_kws[:5]

        theses.append({
            "filename": r["filename"],
            "title": title,
            "keywords": kw_list,
        })

    return theses, keyword_counts, total_with_keywords


def compute_topics_with_llm(client, model, theses, keyword_counts):
    """Prompt LLM (Gemini) to synthesize top 5 department topics from keyword frequencies and titles."""
    top_kw_summary = ", ".join(f"{k} ({c})" for k, c in keyword_counts.most_common(40))
    sample_titles = "\n".join(f"- {t['title']}" for t in theses[:40] if t["title"])

    prompt = f"""You are analyzing thesis topic assignments from the Department of Telecommunications and Media Informatics (TMIT) at Budapest University of Technology and Economics (BME VIK).

Here are the top keywords with frequencies across the department's thesis descriptions:
{top_kw_summary}

Here is a sample of actual thesis titles:
{sample_titles}

Total thesis assignments: {len(theses)}

Identify exactly the Top 5 overarching department topics that best represent the thematic areas of these descriptions.
Rank them from 1 to 5 in descending order of prominence.
For each topic provide:
- rank: Integer 1 to 5
- topic_name: Concise English title (e.g. 'Artificial Intelligence & Machine Learning', 'Cloud & Distributed Systems')
- topic_description: 1-2 sentence description in English explaining what students work on in this area
- thesis_count: Integer estimate of descriptions falling under this topic (sum across all 5 must approximate {len(theses)})
- percentage: Float percentage (0-100) of total descriptions
- top_keywords: List of 4-6 representative keywords for this topic

Return ONLY a JSON object conforming to this structure:
{{
  "topics": [
    {{
      "rank": 1,
      "topic_name": "...",
      "topic_description": "...",
      "thesis_count": 45,
      "percentage": 32.1,
      "top_keywords": ["...", "..."]
    }}, ...
  ]
}}"""

    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config={"response_mime_type": "application/json", "temperature": 0.1},
    )
    raw = (response.text or "").strip()
    data = json.loads(raw)
    return data.get("topics", [])


def compute_topics_deterministic(theses, keyword_counts):
    """Deterministic fallback topic clustering when LLM is unavailable."""
    domains = [
        {
            "name": "Artificial Intelligence & Machine Learning",
            "desc": "Research and applied development of deep learning, LLMs, computer vision, and neural network optimization.",
            "patterns": ["ai", "mi", "llm", "tanulás", "learning", "neurális", "modell", "vision", "látás", "gpt", "rag", "generatív"],
            "kws": ["LLM", "Deep Learning", "Machine Learning", "Computer Vision", "NLP"],
        },
        {
            "name": "Cloud, Serverless & Distributed Systems",
            "desc": "Microservices, Kubernetes orchestration, serverless execution, and cloud-native infrastructure engineering.",
            "patterns": ["felhő", "cloud", "kubernetes", "konténer", "mikroszolgáltatás", "serverless", "elosztott", "infrastruktúra"],
            "kws": ["Kubernetes", "Cloud-native", "Microservices", "Docker", "Serverless"],
        },
        {
            "name": "Mobile Networks & 5G/6G Communications",
            "desc": "Next-generation cellular networks, edge computing, network slicing, QoS management, and low-latency protocols.",
            "patterns": ["hálózat", "5g", "6g", "mobil", "halozat", "edge", "perem", "protokoll", "qos", "szelet"],
            "kws": ["5G", "6G", "Network Slicing", "QoS", "Edge Computing"],
        },
        {
            "name": "Cybersecurity & Runtime Monitoring",
            "desc": "Vulnerability assessment, behavioral security monitoring with Falco/eBPF, and certificate lifecycle management.",
            "patterns": ["biztonság", "security", "sérülékenység", "ebpf", "falco", "tanúsítvány", "ellenőrzés", "monitoring"],
            "kws": ["Cybersecurity", "eBPF", "Falco", "Vulnerability Analysis", "Monitoring"],
        },
        {
            "name": "Signal Processing, Speech & Multimedia Systems",
            "desc": "Acoustic modeling, speech embedding, audio analysis, medical signals (EEG/BCI), and virtual/extended reality.",
            "patterns": ["beszéd", "audio", "akusztikai", "eeg", "bci", "orvosi", "multimédia", "video", "xr", "vr", "grafika"],
            "kws": ["Speech Processing", "Acoustics", "EEG / BCI", "Multimedia", "XR / VR"],
        },
    ]

    total = len(theses) or 1
    scores = [0] * len(domains)
    for t in theses:
        text = (t["title"] + " " + " ".join(t["keywords"])).lower()
        matched = False
        for idx, d in enumerate(domains):
            if any(p in text for p in d["patterns"]):
                scores[idx] += 1
                matched = True
                break
        if not matched:
            scores[0] += 1  # Default to largest domain

    # Sort domains by count
    ranked_indices = sorted(range(len(domains)), key=lambda i: scores[i], reverse=True)
    topics = []
    for rank, idx in enumerate(ranked_indices, start=1):
        cnt = scores[idx]
        topics.append({
            "rank": rank,
            "topic_name": domains[idx]["name"],
            "topic_description": domains[idx]["desc"],
            "thesis_count": cnt,
            "percentage": round((cnt / total) * 100, 1),
            "top_keywords": domains[idx]["kws"],
        })
    return topics


def calculate_distribution_1_to_5(scores, label, metric_key, source_type):
    """Build histogram and average for 1-5 integer scores."""
    if not scores:
        return None
    counts = collections.Counter(scores)
    total = len(scores)
    avg = round(sum(scores) / total, 2)
    min_val = min(scores)
    max_val = max(scores)

    histogram = []
    for score in range(1, 6):
        cnt = counts.get(score, 0)
        pct = round((cnt / total) * 100, 1)
        histogram.append({"bucket": str(score), "count": cnt, "percentage": pct})

    return {
        "metric_key": metric_key,
        "metric_label": label,
        "source_type": source_type,
        "average_value": avg,
        "min_value": min_val,
        "max_value": max_val,
        "total_samples": total,
        "histogram_json": json.dumps(histogram, ensure_ascii=False),
    }


def calculate_distribution_percentage(scores, label, metric_key, source_type):
    """Build histogram and average for 0-100% scores in 10-point decile buckets."""
    if not scores:
        return None
    total = len(scores)
    avg = round(sum(scores) / total, 1)
    min_val = min(scores)
    max_val = max(scores)

    # Buckets: 0-10%, 11-20%, ..., 91-100%
    buckets = [
        ("0–10%", 0, 10),
        ("11–20%", 11, 20),
        ("21–30%", 21, 30),
        ("31–40%", 31, 40),
        ("41–50%", 41, 50),
        ("51–60%", 51, 60),
        ("61–70%", 61, 70),
        ("71–80%", 71, 80),
        ("81–90%", 81, 90),
        ("91–100%", 91, 100),
    ]

    histogram = []
    for name, low, high in buckets:
        cnt = sum(1 for s in scores if low <= s <= high)
        pct = round((cnt / total) * 100, 1)
        histogram.append({"bucket": name, "count": cnt, "percentage": pct})

    return {
        "metric_key": metric_key,
        "metric_label": label,
        "source_type": source_type,
        "average_value": avg,
        "min_value": min_val,
        "max_value": max_val,
        "total_samples": total,
        "histogram_json": json.dumps(histogram, ensure_ascii=False),
    }


ASPECT_LABELS_1_TO_5 = {
    "language_quality": "Language Quality",
    "goal_clarity": "Goal Clarity",
    "task_specificity": "Task Specificity",
    "scope_feasibility": "Scope & Feasibility",
    "degree_appropriateness": "Degree Appropriateness",
    "ai_promptability": "AI Promptability Resistance",
    "structure_conformance": "Canonical Structure Conformance (1-5)",
}

FIT_LABELS = {
    "fit_score_bprof": "BProf Fitting Score (0-100%)",
    "fit_score_bsc": "BSc Fitting Score (0-100%)",
    "fit_score_msc": "MSc Fitting Score (0-100%)",
}


def metric_definition(aspect):
    """Return the display label and scale of a review aspect."""
    if aspect in FIT_LABELS:
        return FIT_LABELS[aspect], "percentage"
    if aspect in ASPECT_LABELS_1_TO_5:
        return ASPECT_LABELS_1_TO_5[aspect], "1_to_5"
    label = aspect.replace("_", " ").strip()
    label = label[:1].upper() + label[1:]
    if aspect.startswith("fit_score_"):
        return f"{label} (0-100%)", "percentage"
    return label, "1_to_5"


def collect_version_counts(conn):
    """Number of versions per thesis, excluding Diplomatervezés 2."""
    rows = conn.execute(
        """
        SELECT COUNT(*) AS versions
        FROM "import"
        WHERE (subject IS NULL OR TRIM(subject) != ?)
        GROUP BY neptun_code
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchall()
    return [int(r["versions"]) for r in rows]


def compute_all_metrics(conn):
    """Calculate distributions for each AI model and aspect, using latest versions only."""
    distributions = []

    # 0. Revision activity: how many versions each thesis has.
    version_counts = collect_version_counts(conn)
    version_dist = calculate_distribution_1_to_5(
        version_counts, "Versions per Thesis", "version_count", "import"
    )
    if version_dist:
        version_dist["model"] = ""
        distributions.append(version_dist)

    # 0b. Domain composition scores (telecommunication / AI / other), extracted per description.
    domain_rows = conn.execute(
        """
        SELECT e.telco_score, e.ai_score, e.other_score
        FROM "extract" AS e
        JOIN "import" AS i ON i.filename = e.filename
        JOIN (
            SELECT neptun_code, MAX(version) AS version
            FROM "import"
            GROUP BY neptun_code
        ) AS latest ON latest.neptun_code = i.neptun_code AND latest.version = i.version
        WHERE (e.telco_score IS NOT NULL OR e.ai_score IS NOT NULL OR e.other_score IS NOT NULL)
          AND (i.subject IS NULL OR TRIM(i.subject) != ?)
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchall()

    domain_metric_defs = [
        ("telco_score", "Telecommunication Score (0-100%)"),
        ("ai_score", "Artificial Intelligence Score (0-100%)"),
        ("other_score", "Other Domains Score (0-100%)"),
    ]
    domain_averages = {}
    for key, label in domain_metric_defs:
        scores = [int(r[key]) for r in domain_rows if r[key] is not None]
        dist = calculate_distribution_percentage(scores, label, key, "extract")
        if dist:
            dist["model"] = ""
            distributions.append(dist)
            domain_averages[key] = dist["average_value"]

    # 1. Review aspect scores, computed separately for every AI model.
    aspect_rows = conn.execute(
        """
        SELECT r.reviewer, r.aspect, r.score, i.degree
        FROM reviews AS r
        JOIN "import" AS i ON i.neptun_code = r.neptun_code AND i.version = r.version
        JOIN (
            SELECT neptun_code, MAX(version) AS version
            FROM "import"
            GROUP BY neptun_code
        ) AS latest ON latest.neptun_code = i.neptun_code AND latest.version = i.version
        WHERE r.score IS NOT NULL AND r.aspect != 'remark'
          AND (i.subject IS NULL OR TRIM(i.subject) != ?)
        ORDER BY r.reviewer, r.aspect
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchall()

    FIT_DEGREE_BY_ASPECT = {
        "fit_score_bprof": "BProf",
        "fit_score_bsc": "BSc",
        "fit_score_msc": "MSc",
    }
    scores_by_model = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in aspect_rows:
        aspect = r["aspect"]
        # In statistics, a fit score counts only for descriptions of its own degree level.
        if aspect in FIT_DEGREE_BY_ASPECT and r["degree"] != FIT_DEGREE_BY_ASPECT[aspect]:
            continue
        scores_by_model[r["reviewer"]][aspect].append(int(r["score"]))

    preferred_order = list(ASPECT_LABELS_1_TO_5) + list(FIT_LABELS)
    for model in sorted(scores_by_model):
        aspects = scores_by_model[model]
        ordered_aspects = [a for a in preferred_order if a in aspects]
        ordered_aspects.extend(sorted(a for a in aspects if a not in preferred_order))
        for aspect_key in ordered_aspects:
            label, scale = metric_definition(aspect_key)
            if scale == "percentage":
                dist = calculate_distribution_percentage(
                    aspects[aspect_key], label, aspect_key, "review"
                )
            else:
                dist = calculate_distribution_1_to_5(
                    aspects[aspect_key], label, aspect_key, "review"
                )
            if dist:
                dist["model"] = model
                distributions.append(dist)

    return distributions


def pooled_distribution(distributions, metric_key):
    """Combine the same aspect across models for department-level fun facts."""
    parts = [
        d for d in distributions
        if d["metric_key"] == metric_key and d.get("source_type") == "review"
    ]
    if not parts:
        return None
    total = sum(d["total_samples"] for d in parts)
    if not total:
        return None
    buckets = collections.Counter()
    for d in parts:
        for bucket in json.loads(d["histogram_json"]):
            buckets[bucket["bucket"]] += bucket["count"]
    order = [bucket["bucket"] for bucket in json.loads(parts[0]["histogram_json"])]
    histogram = [
        {
            "bucket": bucket,
            "count": buckets.get(bucket, 0),
            "percentage": round(buckets.get(bucket, 0) / total * 100, 1),
        }
        for bucket in order
    ]
    return {
        "average_value": round(
            sum(d["average_value"] * d["total_samples"] for d in parts) / total, 2
        ),
        "total_samples": total,
        "histogram_json": json.dumps(histogram, ensure_ascii=False),
    }


def generate_fun_facts(conn, theses, keyword_counts, distributions):
    """Generate intriguing data-driven trivia and facts about the thesis assignments."""
    facts = []

    # 1. Top keyword
    if keyword_counts:
        top_kw, top_count = keyword_counts.most_common(1)[0]
        facts.append({
            "category": "topics",
            "title": "Most Frequent Technology Keyword",
            "fact_text": f"'{top_kw}' is the most commonly recurring technical keyword, appearing across {top_count} thesis descriptions.",
            "highlight_stat": f"{top_kw} ({top_count}x)",
        })

    # 2. Language quality insight (pooled across models; per-model cards are separate)
    lq = pooled_distribution(distributions, "language_quality")
    if lq:
        hist = json.loads(lq["histogram_json"])
        pct_5 = next((b["percentage"] for b in hist if b["bucket"] == "5"), 0)
        pct_low = sum(b["percentage"] for b in hist if b["bucket"] in ("1", "2"))
        facts.append({
            "category": "quality",
            "title": "Language Quality Average",
            "fact_text": f"The average language quality score across all AI model reviews is {lq['average_value']} / 5. Exactly {pct_5}% received an exceptional 5/5 score, while {pct_low}% showed noticeable linguistic defects.",
            "highlight_stat": f"{lq['average_value']} / 5.0",
        })

    # 3. Structure Conformance insight (pooled across models)
    sc = pooled_distribution(distributions, "structure_conformance")
    if sc:
        hist = json.loads(sc["histogram_json"])
        pct_well_structured = sum(b["percentage"] for b in hist if b["bucket"] in ("4", "5"))
        facts.append({
            "category": "methodology",
            "title": "Adherence to 5-Phase Methodology",
            "fact_text": f"{pct_well_structured}% of analyzed descriptions strictly follow the canonical 5-phase engineering methodology (Literature, Design, Implementation, Verification, Documentation) with average score {sc['average_value']} / 5.",
            "highlight_stat": f"{pct_well_structured}% compliant",
        })

    # 4. Average task count (latest versions only)
    task_row = conn.execute(
        """
        SELECT tasks_json
        FROM extract AS e
        JOIN "import" AS i ON i.filename = e.filename
        JOIN (
            SELECT neptun_code, MAX(version) AS version
            FROM "import"
            GROUP BY neptun_code
        ) AS latest ON latest.neptun_code = i.neptun_code AND latest.version = i.version
        WHERE e.tasks_json IS NOT NULL AND (i.subject IS NULL OR TRIM(i.subject) != ?)
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchall()
    if task_row:
        counts = []
        for r in task_row:
            try:
                tasks = json.loads(r[0])
                if isinstance(tasks, list):
                    counts.append(len(tasks))
            except Exception:
                pass
        if counts:
            avg_tasks = round(sum(counts) / len(counts), 1)
            facts.append({
                "category": "trivia",
                "title": "Average Tasks per Thesis",
                "fact_text": f"Supervisors specify an average of {avg_tasks} individual tasks per thesis assignment, ranging from {min(counts)} to {max(counts)} subtasks.",
                "highlight_stat": f"{avg_tasks} tasks",
            })

    # 5. AI Promptability insight (pooled across models)
    ai_dist = pooled_distribution(distributions, "ai_promptability")
    if ai_dist:
        hist = json.loads(ai_dist["histogram_json"])
        pct_robust = sum(b["percentage"] for b in hist if b["bucket"] in ("4", "5"))
        facts.append({
            "category": "ai",
            "title": "Resistance to Pure AI Generation",
            "fact_text": f"{pct_robust}% of assignments require substantial independent engineering, integration, or hardware verification that cannot be fulfilled by giving an AI assistant a one-shot prompt.",
            "highlight_stat": f"{pct_robust}% AI-resistant",
        })

    # 6. Overall description count
    facts.append({
        "category": "summary",
        "title": "Active Department Thesis Portfolio",
        "fact_text": f"The department currently manages {len(theses)} active bachelor and master thesis descriptions across multiple specializations.",
        "highlight_stat": f"{len(theses)} active theses",
    })

    # 7. Domain composition overall (telecommunication / AI / other)
    domain_row = conn.execute(
        """
        SELECT AVG(e.telco_score) AS telco_avg, AVG(e.ai_score) AS ai_avg, AVG(e.other_score) AS other_avg, COUNT(*) AS n
        FROM "extract" AS e
        JOIN "import" AS i ON i.filename = e.filename
        JOIN (
            SELECT neptun_code, MAX(version) AS version
            FROM "import"
            GROUP BY neptun_code
        ) AS latest ON latest.neptun_code = i.neptun_code AND latest.version = i.version
        WHERE (e.telco_score IS NOT NULL OR e.ai_score IS NOT NULL OR e.other_score IS NOT NULL)
          AND (i.subject IS NULL OR TRIM(i.subject) != ?)
        """,
        (EXCLUDED_SUBJECT,),
    ).fetchone()
    if domain_row and domain_row["n"]:
        telco_avg = round(domain_row["telco_avg"] or 0, 1)
        ai_avg = round(domain_row["ai_avg"] or 0, 1)
        other_avg = round(domain_row["other_avg"] or 0, 1)
        facts.append({
            "category": "topics",
            "title": "Department Domain Composition",
            "fact_text": f"Across {domain_row['n']} thesis descriptions, the average domain composition is {telco_avg}% telecommunication, {ai_avg}% artificial intelligence, and {other_avg}% other.",
            "highlight_stat": f"Telco {telco_avg}% / AI {ai_avg}% / Other {other_avg}%",
        })

    # 7. Revision activity: versions per latest thesis
    version_counts = collect_version_counts(conn)
    if version_counts:
        total_versions = sum(version_counts)
        avg_versions = round(total_versions / len(version_counts), 2)
        revised = sum(1 for count in version_counts if count > 1)
        revised_pct = round(revised / len(version_counts) * 100, 1)
        facts.append({
            "category": "portfolio",
            "title": "Description Revision Activity",
            "fact_text": f"The {len(version_counts)} latest thesis descriptions have {total_versions} versions in total: {avg_versions} versions per thesis on average. {revised} descriptions ({revised_pct}%) have at least one revision, with up to {max(version_counts)} versions.",
            "highlight_stat": f"{avg_versions} versions / thesis",
        })

    return facts


def save_statistics(conn, topics, distributions, fun_facts):
    """Write computed topics, distributions, and fun facts into database tables."""
    with conn:
        # 1. description_topics
        conn.execute("DELETE FROM description_topics")
        for t in topics:
            conn.execute(
                """
                INSERT INTO description_topics (rank, topic_name, topic_description, thesis_count, percentage, top_keywords_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    t["rank"],
                    t["topic_name"],
                    t.get("topic_description", ""),
                    t["thesis_count"],
                    t["percentage"],
                    json.dumps(t.get("top_keywords", []), ensure_ascii=False),
                ),
            )

        # 2. description_metric_distributions
        conn.execute("DELETE FROM description_metric_distributions")
        for d in distributions:
            conn.execute(
                """
                INSERT INTO description_metric_distributions
                (metric_key, model, metric_label, source_type, average_value, min_value, max_value, total_samples, histogram_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["metric_key"],
                    d.get("model", ""),
                    d["metric_label"],
                    d["source_type"],
                    d["average_value"],
                    d["min_value"],
                    d["max_value"],
                    d["total_samples"],
                    d["histogram_json"],
                ),
            )

        # 3. description_fun_facts
        conn.execute("DELETE FROM description_fun_facts")
        for f in fun_facts:
            conn.execute(
                """
                INSERT INTO description_fun_facts (category, title, fact_text, highlight_stat)
                VALUES (?, ?, ?, ?)
                """,
                (f["category"], f["title"], f["fact_text"], f.get("highlight_stat", "")),
            )


def main():
    parser = argparse.ArgumentParser(description="Compute description statistics, topic rankings, and histograms.")
    parser.add_argument("--database", "-d", default=DATABASE_PATH, help=f"Path to SQLite database (default: {DATABASE_PATH})")
    parser.add_argument("--model", "-m", default="gemini-3.5-flash-lite", help="Google GenAI model ID for topic clustering (default: gemini-3.5-flash-lite)")
    parser.add_argument("--dry-run", action="store_true", help="Print computed stats without saving to database")
    args = parser.parse_args()

    conn = open_db(args.database)
    print(f"Connected to database at {args.database}")

    theses, keyword_counts, kw_count = collect_keywords_and_theses(conn)
    print(f"Analyzed {len(theses)} thesis descriptions ({kw_count} with structured keywords, {len(keyword_counts)} distinct terms).")

    # Try LLM synthesis for topics if API key is configured
    topics = []
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client()
            print(f"Calling {args.model} to synthesize Top 5 department topics...")
            topics = compute_topics_with_llm(client, args.model, theses, keyword_counts)
        except Exception as e:
            print(f"WARNING: LLM topic clustering failed ({e}); falling back to deterministic clustering.")

    if not topics:
        print("Using deterministic keyword clustering for Top 5 topics.")
        topics = compute_topics_deterministic(theses, keyword_counts)

    print("\nTop 5 Department Topics:")
    for t in topics:
        print(f"  #{t['rank']}: {t['topic_name']} - {t['thesis_count']} theses ({t['percentage']}%)")

    # Compute metric distributions and histograms
    distributions = compute_all_metrics(conn)
    print(f"\nCalculated distributions for {len(distributions)} metrics:")
    for d in distributions:
        model = d.get("model")
        prefix = f"{model} / " if model else ""
        print(f"  - {prefix}{d['metric_label']}: avg={d['average_value']} (samples: {d['total_samples']})")

    # Generate fun facts
    fun_facts = generate_fun_facts(conn, theses, keyword_counts, distributions)
    print(f"\nGenerated {len(fun_facts)} fun facts & insights.")
    for f in fun_facts:
        print(f"  * [{f['category'].upper()}] {f['title']}: {f['highlight_stat']}")

    if args.dry_run:
        print("\nDry-run mode: no database changes made.")
    else:
        save_statistics(conn, topics, distributions, fun_facts)
        print("\nSuccessfully updated statistics tables in SQLite database.")

    conn.close()


if __name__ == "__main__":
    main()
