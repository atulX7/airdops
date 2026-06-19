"""
Enterprise-grade database models for PrimeData.

This module defines enterprise-ready database models with proper
audit trails, security, and compliance features.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class RuleSeverity(PyEnum):
    """Data quality rule severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleStatus(PyEnum):
    """Rule lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class AuditAction(PyEnum):
    """Audit trail actions."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACTIVATE = "activate"
    DEPRECATE = "deprecate"
    ARCHIVE = "archive"


class DataQualityRule(Base):
    """Enterprise-grade data quality rules with full audit trail."""

    __tablename__ = "data_quality_rules"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)

    # Rule metadata
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    rule_type = Column(String(50), nullable=False)  # required_fields, max_duplicate_rate, etc.
    severity = Column(Enum(RuleSeverity), nullable=False, default=RuleSeverity.ERROR)
    status = Column(Enum(RuleStatus), nullable=False, default=RuleStatus.DRAFT)

    # Rule configuration (JSON)
    configuration = Column(JSON, nullable=False)

    # Versioning and lifecycle
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    parent_rule_id = Column(UUID(as_uuid=True), ForeignKey("data_quality_rules.id"), nullable=True)

    # Enterprise features
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)  # User who created the rule
    updated_by = Column(UUID(as_uuid=True), nullable=True)  # User who last updated
    approved_by = Column(UUID(as_uuid=True), nullable=True)  # User who approved for production

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)

    # Compliance and governance
    compliance_tags = Column(JSON, nullable=True)  # GDPR, SOX, HIPAA tags
    business_owner = Column(String(255), nullable=True)
    technical_owner = Column(String(255), nullable=True)

    # Relationships
    product = relationship("Product", back_populates="data_quality_rules")
    workspace = relationship("Workspace", back_populates="data_quality_rules")
    audit_logs = relationship("DataQualityRuleAudit", back_populates="rule")

    def __repr__(self):
        return f"<DataQualityRule(id={self.id}, name='{self.name}', type='{self.rule_type}')>"


class DataQualityRuleAudit(Base):
    """Complete audit trail for data quality rule changes."""

    __tablename__ = "data_quality_rule_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("data_quality_rules.id"), nullable=False)

    # Audit metadata
    action = Column(Enum(AuditAction), nullable=False)
    changed_by = Column(UUID(as_uuid=True), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Change tracking
    old_values = Column(JSON, nullable=True)  # Previous values
    new_values = Column(JSON, nullable=True)  # New values
    change_reason = Column(Text, nullable=True)  # Business reason for change

    # IP and session tracking
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(255), nullable=True)

    # Relationships
    rule = relationship("DataQualityRule", back_populates="audit_logs")

    def __repr__(self):
        return f"<DataQualityRuleAudit(rule_id={self.rule_id}, action='{self.action}')>"


class DataQualityRuleSet(Base):
    """Enterprise rule sets for governance and compliance."""

    __tablename__ = "data_quality_rule_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)

    # Rule set metadata
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    version = Column(String(20), nullable=False)  # e.g., "1.0", "2.1"

    # Governance
    compliance_framework = Column(String(100), nullable=True)  # GDPR, SOX, HIPAA, etc.
    business_unit = Column(String(100), nullable=True)
    data_classification = Column(String(50), nullable=True)  # Public, Internal, Confidential, Restricted

    # Lifecycle
    status = Column(Enum(RuleStatus), nullable=False, default=RuleStatus.DRAFT)
    is_active = Column(Boolean, nullable=False, default=False)

    # Ownership
    created_by = Column(UUID(as_uuid=True), nullable=False)
    approved_by = Column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_until = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("Workspace")
    rule_assignments = relationship("DataQualityRuleAssignment", back_populates="rule_set")

    def __repr__(self):
        return f"<DataQualityRuleSet(id={self.id}, name='{self.name}', version='{self.version}')>"


class DataQualityRuleAssignment(Base):
    """Assignment of rules to products via rule sets."""

    __tablename__ = "data_quality_rule_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_set_id = Column(UUID(as_uuid=True), ForeignKey("data_quality_rule_sets.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    # Assignment metadata
    assigned_by = Column(UUID(as_uuid=True), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Override settings
    is_override = Column(Boolean, nullable=False, default=False)
    override_reason = Column(Text, nullable=True)

    # Relationships
    rule_set = relationship("DataQualityRuleSet", back_populates="rule_assignments")
    product = relationship("Product")

    def __repr__(self):
        return f"<DataQualityRuleAssignment(rule_set_id={self.rule_set_id}, product_id={self.product_id})>"


class DataQualityComplianceReport(Base):
    """Enterprise compliance reporting."""

    __tablename__ = "data_quality_compliance_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)

    # Report metadata
    report_name = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)  # compliance, audit, executive
    compliance_framework = Column(String(100), nullable=True)

    # Report period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Report data
    report_data = Column(JSON, nullable=True)  # Small summary only (full data in S3)
    report_data_path = Column(String(1000), nullable=False)  # S3 path to full report data
    summary = Column(Text, nullable=True)

    # Generation metadata
    generated_by = Column(UUID(as_uuid=True), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workspace = relationship("Workspace")

    def __repr__(self):
        return f"<DataQualityComplianceReport(id={self.id}, name='{self.report_name}')>"
