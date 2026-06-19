"""
Data Quality Rules Schema for PrimeData.

This module defines the schema for declarative data quality rules that can be
applied to products to ensure data quality standards are met.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class RuleSeverity(str, Enum):
    """Severity levels for data quality rules."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DataQualityRule(BaseModel):
    """Base class for data quality rules."""

    name: str = Field(..., description="Human-readable name for the rule")
    description: str = Field(..., description="Description of what this rule checks")
    severity: RuleSeverity = Field(default=RuleSeverity.ERROR, description="Severity level")
    enabled: bool = Field(default=True, description="Whether this rule is enabled")


class RequiredFieldsRule(DataQualityRule):
    """Rule to check for required fields in documents."""

    rule_type: str = Field(default="required_fields", description="Type of rule")
    required_fields: List[str] = Field(..., description="List of required field names")

    @validator("required_fields")
    def validate_required_fields(cls, v):
        if not v:
            raise ValueError("At least one required field must be specified")
        return v


class MaxDuplicateRateRule(DataQualityRule):
    """Rule to limit the maximum duplicate rate in the dataset."""

    rule_type: str = Field(default="max_duplicate_rate", description="Type of rule")
    max_duplicate_rate: float = Field(..., ge=0.0, le=1.0, description="Maximum allowed duplicate rate (0.0-1.0)")

    @validator("max_duplicate_rate")
    def validate_duplicate_rate(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Duplicate rate must be between 0.0 and 1.0")
        return v


class MinChunkCoverageRule(DataQualityRule):
    """Rule to ensure minimum chunk coverage of the original content."""

    rule_type: str = Field(default="min_chunk_coverage", description="Type of rule")
    min_chunk_coverage: float = Field(..., ge=0.0, le=1.0, description="Minimum required chunk coverage (0.0-1.0)")

    @validator("min_chunk_coverage")
    def validate_chunk_coverage(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Chunk coverage must be between 0.0 and 1.0")
        return v


class BadExtensionsRule(DataQualityRule):
    """Rule to reject files with bad extensions."""

    rule_type: str = Field(default="bad_extensions", description="Type of rule")
    bad_extensions: List[str] = Field(..., description="List of file extensions to reject")

    @validator("bad_extensions")
    def validate_bad_extensions(cls, v):
        if not v:
            raise ValueError("At least one bad extension must be specified")
        # Ensure extensions start with dot
        normalized = []
        for ext in v:
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext.lower())
        return normalized


class MinFreshnessRule(DataQualityRule):
    """Rule to ensure data is not too old."""

    rule_type: str = Field(default="min_freshness", description="Type of rule")
    min_freshness_days: int = Field(..., ge=1, description="Minimum freshness in days")

    @validator("min_freshness_days")
    def validate_freshness_days(cls, v):
        if v < 1:
            raise ValueError("Minimum freshness must be at least 1 day")
        return v


class FileSizeRule(DataQualityRule):
    """Rule to check file size limits."""

    rule_type: str = Field(default="file_size", description="Type of rule")
    max_file_size_mb: float = Field(..., gt=0, description="Maximum file size in MB")
    min_file_size_kb: Optional[float] = Field(None, ge=0, description="Minimum file size in KB")

    @validator("max_file_size_mb")
    def validate_max_file_size(cls, v):
        if v <= 0:
            raise ValueError("Maximum file size must be greater than 0")
        return v


class ContentLengthRule(DataQualityRule):
    """Rule to check content length limits."""

    rule_type: str = Field(default="content_length", description="Type of rule")
    min_content_length: Optional[int] = Field(None, ge=0, description="Minimum content length in characters")
    max_content_length: Optional[int] = Field(None, gt=0, description="Maximum content length in characters")

    @validator("max_content_length")
    def validate_content_length(cls, v, values):
        if v is not None and "min_content_length" in values and values["min_content_length"] is not None:
            if v <= values["min_content_length"]:
                raise ValueError("Maximum content length must be greater than minimum content length")
        return v


class DataQualityRules(BaseModel):
    """Container for all data quality rules for a product."""

    product_id: str = Field(..., description="ID of the product these rules apply to")
    version: int = Field(..., description="Version of the rules")
    created_at: str = Field(..., description="When these rules were created")
    updated_at: str = Field(..., description="When these rules were last updated")

    # Rule collections
    required_fields_rules: List[RequiredFieldsRule] = Field(default_factory=list)
    max_duplicate_rate_rules: List[MaxDuplicateRateRule] = Field(default_factory=list)
    min_chunk_coverage_rules: List[MinChunkCoverageRule] = Field(default_factory=list)
    bad_extensions_rules: List[BadExtensionsRule] = Field(default_factory=list)
    min_freshness_rules: List[MinFreshnessRule] = Field(default_factory=list)
    file_size_rules: List[FileSizeRule] = Field(default_factory=list)
    content_length_rules: List[ContentLengthRule] = Field(default_factory=list)

    def get_all_rules(self) -> List[DataQualityRule]:
        """Get all rules as a flat list."""
        all_rules = []
        all_rules.extend(self.required_fields_rules)
        all_rules.extend(self.max_duplicate_rate_rules)
        all_rules.extend(self.min_chunk_coverage_rules)
        all_rules.extend(self.bad_extensions_rules)
        all_rules.extend(self.min_freshness_rules)
        all_rules.extend(self.file_size_rules)
        all_rules.extend(self.content_length_rules)
        return all_rules

    def get_enabled_rules(self) -> List[DataQualityRule]:
        """Get all enabled rules."""
        return [rule for rule in self.get_all_rules() if rule.enabled]

    def get_rules_by_severity(self, severity: RuleSeverity) -> List[DataQualityRule]:
        """Get rules filtered by severity."""
        return [rule for rule in self.get_all_rules() if rule.severity == severity]


class DataQualityViolation(BaseModel):
    """Represents a data quality violation."""

    rule_name: str = Field(..., description="Name of the rule that was violated")
    rule_type: str = Field(..., description="Type of rule that was violated")
    severity: RuleSeverity = Field(..., description="Severity of the violation")
    message: str = Field(..., description="Human-readable violation message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional violation details")
    affected_count: int = Field(default=0, description="Number of items affected by this violation")
    total_count: int = Field(default=0, description="Total number of items checked")

    @property
    def violation_rate(self) -> float:
        """Calculate the violation rate."""
        if self.total_count == 0:
            return 0.0
        return self.affected_count / self.total_count


class DataQualityReport(BaseModel):
    """Complete data quality report for a product version."""

    product_id: str = Field(..., description="ID of the product")
    version: int = Field(..., description="Version of the product")
    pipeline_run_id: str = Field(..., description="ID of the pipeline run")
    created_at: str = Field(..., description="When the report was generated")

    violations: List[DataQualityViolation] = Field(default_factory=list)
    total_items_checked: int = Field(default=0, description="Total number of items checked")
    total_violations: int = Field(default=0, description="Total number of violations")

    @property
    def has_violations(self) -> bool:
        """Check if there are any violations."""
        return len(self.violations) > 0

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level violations."""
        return any(v.severity == RuleSeverity.ERROR for v in self.violations)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warning-level violations."""
        return any(v.severity == RuleSeverity.WARNING for v in self.violations)

    @property
    def overall_quality_score(self) -> float:
        """Calculate overall quality score (0.0-1.0)."""
        if self.total_items_checked == 0:
            return 1.0

        error_violations = sum(v.affected_count for v in self.violations if v.severity == RuleSeverity.ERROR)
        warning_violations = sum(v.affected_count for v in self.violations if v.severity == RuleSeverity.WARNING)

        # Weight errors more heavily than warnings
        total_penalty = (error_violations * 2) + warning_violations
        max_possible_penalty = self.total_items_checked * 2

        if max_possible_penalty == 0:
            return 1.0

        return max(0.0, 1.0 - (total_penalty / max_possible_penalty))
