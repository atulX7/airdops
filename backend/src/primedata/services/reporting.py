"""
Reporting service for PrimeData.

Generates validation summaries (CSV) and trust reports (PDF) from metrics.
"""

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    logger.warning("pandas not available, CSV generation will be limited")

try:
    import matplotlib

    matplotlib.use("Agg")  # Non-GUI backend
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available, PDF generation will be disabled")


def generate_validation_summary(
    metrics: List[Dict[str, Any]],
    threshold: float = 70.0,
) -> str:
    """
    Generate validation summary CSV from metrics.

    Args:
        metrics: List of metric dictionaries (one per chunk)
        threshold: AI Trust Score threshold for categorization

    Returns:
        CSV content as string
    """
    if not HAS_PANDAS:
        raise RuntimeError("pandas is required for validation summary generation")

    if not metrics:
        logger.warning("No metrics provided for validation summary")
        return ""

    df = pd.DataFrame(metrics)

    # Helper to get metric value from canonical schema
    def get_metric_from_row(row: Dict[str, Any], canonical_key: str, legacy_key: Optional[str] = None) -> float:
        """Get metric value from row, checking canonical key first, then legacy_aliases."""
        if canonical_key and canonical_key in row:
            return float(row[canonical_key])
        if legacy_key and legacy_key in row:
            return float(row[legacy_key])
        if "legacy_aliases" in row and isinstance(row["legacy_aliases"], dict):
            if legacy_key and legacy_key in row["legacy_aliases"]:
                return float(row["legacy_aliases"][legacy_key])
        return 0.0

    # Check if ai_trust_score or AI_Trust_Score exists (required for categorization)
    has_trust_score = "ai_trust_score" in df.columns or "AI_Trust_Score" in df.columns
    if not has_trust_score:
        logger.warning("ai_trust_score or AI_Trust_Score column not found in metrics, cannot generate validation summary")
        return ""

    # Categorize: AI Ready if score >= threshold
    # Use canonical key if available, otherwise legacy
    if "ai_trust_score" in df.columns:
        df["Category"] = df["ai_trust_score"].apply(lambda x: "AI Ready" if x >= threshold else "Non-AI Ready")
    else:
        df["Category"] = df["AI_Trust_Score"].apply(lambda x: "AI Ready" if x >= threshold else "Non-AI Ready")

    # Define expected columns with their display names (canonical first, then legacy)
    expected_columns = {
        # Canonical keys
        "ai_trust_score": "Avg Trust Score",
        "completeness": "Avg Completeness",
        "text_integrity": "Avg Text Integrity",
        "timeliness": "Avg Timeliness",
        "metadata_completeness": "Avg Metadata %",
        # Legacy keys (for backward compatibility)
        "AI_Trust_Score": "Avg Trust Score",
        "GPT_Confidence": "Avg GPT Confidence",
        "Completeness": "Avg Completeness",
        "Accuracy": "Avg Accuracy (Legacy)",
        "Quality": "Avg Quality",
        "Secure": "Avg Secure",
        "Timeliness": "Avg Timeliness",
        "Metadata_Presence": "Avg Metadata %",
        "Audience_Intentionality": "Avg Audience Intent",
        "Diversity": "Avg Diversity",
        "Context_Quality": "Avg Context Quality",
        "Audience_Accessibility": "Avg Audience Access",
        "KnowledgeBase_Ready": "Avg KB Readiness",
    }

    # Only aggregate columns that actually exist in the DataFrame (excluding AI_Trust_Score from aggregation)
    # AI_Trust_Score is used for categorization but should still be included in summary
    agg_dict = {}
    rename_dict = {}
    for col_name, display_name in expected_columns.items():
        if col_name in df.columns:
            agg_dict[col_name] = "mean"
            rename_dict[col_name] = display_name

    if not agg_dict:
        logger.warning("No valid metric columns found for aggregation")
        return ""

    # Compute summary stats
    summary = df.groupby("Category").agg(agg_dict).rename(columns=rename_dict)

    # Convert to CSV string
    csv_buffer = io.StringIO()
    summary.to_csv(csv_buffer, index=True)
    csv_content = csv_buffer.getvalue()
    csv_buffer.close()

    logger.info(f"Generated validation summary with {len(summary)} categories")
    return csv_content


def generate_trust_report(
    metrics: List[Dict[str, Any]],
    threshold: float = 0.75,  # Normalized to [0,1]
) -> bytes:
    """
    Generate PDF trust report from metrics.

    Args:
        metrics: List of metric dictionaries (one per chunk)
        threshold: AI Trust Score threshold for categorization (0-100 scale)

    Returns:
        PDF content as bytes
    """
    if not HAS_MATPLOTLIB:
        raise RuntimeError("matplotlib is required for PDF report generation")

    if not metrics:
        logger.warning("No metrics provided for trust report")
        return b""

    # Helper to get metric value from canonical schema (checks legacy_aliases if needed)
    def get_metric_value(metric_dict: Dict[str, Any], canonical_key: str, legacy_key: Optional[str] = None) -> float:
        """Get metric value from chunk-level metrics, checking canonical key first, then legacy_aliases."""
        # Try canonical key first
        if canonical_key and canonical_key in metric_dict:
            return float(metric_dict[canonical_key])
        # Try legacy key at top-level (backward compatibility)
        if legacy_key and legacy_key in metric_dict:
            return float(metric_dict[legacy_key])
        # Try legacy_aliases
        if "legacy_aliases" in metric_dict and isinstance(metric_dict["legacy_aliases"], dict):
            if legacy_key and legacy_key in metric_dict["legacy_aliases"]:
                return float(metric_dict["legacy_aliases"][legacy_key])
        return 0.0

    # Choose the labels to plot (using canonical keys where available)
    # Map: (canonical_key, legacy_key, display_label)
    label_mappings = [
        ("completeness", "Completeness", "completeness"),
        ("text_integrity", "Accuracy", "text_integrity"),
        (None, "Secure", "Secure"),  # Secure only exists as legacy
        (None, "Quality", "Quality"),  # Quality only exists as legacy
        ("timeliness", "Timeliness", "timeliness"),
    ]

    ai_vals, non_vals = [], []

    # Compute average per-metric for AI-ready vs non-ready
    for canonical_key, legacy_key, display_label in label_mappings:
        # Get AI_Trust_Score for filtering
        ai_list = [
            get_metric_value(x, canonical_key, legacy_key)
            for x in metrics
            if get_metric_value(x, "ai_trust_score", "AI_Trust_Score") >= threshold
        ]
        non_list = [
            get_metric_value(x, canonical_key, legacy_key)
            for x in metrics
            if get_metric_value(x, "ai_trust_score", "AI_Trust_Score") < threshold
        ]

        ai_vals.append(sum(ai_list) / len(ai_list) if ai_list else 0)
        non_vals.append(sum(non_list) / len(non_list) if non_list else 0)

    # Extract display labels for chart
    labels = [display_label for _, _, display_label in label_mappings]

    # Prepare bar chart
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([i - 0.2 for i in x], ai_vals, width=0.4, label="AI Ready")
    ax.bar([i + 0.2 for i in x], non_vals, width=0.4, label="Non-AI Ready")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Avg Score")
    ax.set_title("AI Trust Metric Comparison")
    ax.legend()

    # Save to PDF bytes
    pdf_buffer = io.BytesIO()
    with PdfPages(pdf_buffer) as out:
        out.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Second page with recommendations
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.axis("off")
        report = "\n".join(
            [
                "🟢 AI-Ready Data: Score ≥ 75% — Recommended for AI/chatbot ingestion.",
                "🟡 Medium Trust: Score 50–74% — Needs cleanup or review.",
                "🔴 Non-AI-Ready: Score < 50% — Not suitable without transformation.",
            ]
        )
        ax2.text(0, 1, report, va="top", fontsize=12, transform=ax2.transAxes)
        out.savefig(fig2, bbox_inches="tight")
        plt.close(fig2)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    logger.info(f"Generated trust report PDF ({len(pdf_bytes)} bytes)")
    return pdf_bytes
