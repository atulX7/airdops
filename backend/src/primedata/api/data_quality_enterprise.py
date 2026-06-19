"""
Enterprise-grade Data Quality API endpoints for PrimeData.

This module provides enterprise-ready REST API endpoints for managing
data quality rules with full audit trails, compliance, and governance.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from ..core.scope import ensure_product_access, ensure_workspace_access
from ..core.security import get_current_user
from ..core.user_utils import get_user_id
from ..db.database import get_db
from ..db.models import DqViolation, Product, Workspace
from ..db.models_enterprise import (
    AuditAction,
    DataQualityComplianceReport,
    DataQualityRule,
    DataQualityRuleAssignment,
    DataQualityRuleAudit,
    DataQualityRuleSet,
    RuleSeverity,
    RuleStatus,
)

router = APIRouter(prefix="/api/v1/enterprise/data-quality", tags=["enterprise-data-quality"])


# Request/Response Models
class DataQualityRuleCreateRequest(BaseModel):
    """Request model for creating data quality rules."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    rule_type: str = Field(..., min_length=1, max_length=50)
    severity: RuleSeverity = Field(default=RuleSeverity.ERROR)
    configuration: Dict[str, Any] = Field(..., description="Rule-specific configuration")
    compliance_tags: Optional[List[str]] = Field(None, description="Compliance tags (GDPR, SOX, etc.)")
    business_owner: Optional[str] = Field(None, max_length=255)
    technical_owner: Optional[str] = Field(None, max_length=255)


class DataQualityRuleUpdateRequest(BaseModel):
    """Request model for updating data quality rules."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    severity: Optional[RuleSeverity] = None
    configuration: Optional[Dict[str, Any]] = None
    compliance_tags: Optional[List[str]] = None
    business_owner: Optional[str] = Field(None, max_length=255)
    technical_owner: Optional[str] = Field(None, max_length=255)
    change_reason: Optional[str] = Field(None, description="Business reason for change")


class DataQualityRuleResponse(BaseModel):
    """Response model for data quality rules."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    product_id: UUID
    workspace_id: UUID
    name: str
    description: str
    rule_type: str
    severity: RuleSeverity
    status: RuleStatus
    configuration: Dict[str, Any]
    version: int
    is_current: bool
    enabled: bool
    compliance_tags: Optional[List[str]]
    business_owner: Optional[str]
    technical_owner: Optional[str]
    created_by: UUID
    updated_by: Optional[UUID]
    approved_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    activated_at: Optional[datetime]
    deprecated_at: Optional[datetime]


class DataQualityRuleAuditResponse(BaseModel):
    """Response model for audit trail."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    rule_id: UUID
    action: AuditAction
    changed_by: UUID
    changed_at: datetime
    old_values: Optional[Dict[str, Any]]
    new_values: Optional[Dict[str, Any]]
    change_reason: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]


class ComplianceReportRequest(BaseModel):
    """Request model for generating compliance reports."""

    report_name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., description="compliance, audit, executive")
    compliance_framework: Optional[str] = Field(None, description="GDPR, SOX, HIPAA, etc.")
    period_start: datetime
    period_end: datetime
    include_audit_trail: bool = Field(default=True)
    include_violations: bool = Field(default=True)
    include_metrics: bool = Field(default=True)


# API Endpoints
@router.post("/rules", response_model=DataQualityRuleResponse)
async def create_data_quality_rule(
    request: DataQualityRuleCreateRequest,
    product_id: UUID,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new data quality rule with full audit trail."""
    try:
        # Verify product exists and user has access
        product = ensure_product_access(db, http_request, product_id)

        # Create new rule
        rule = DataQualityRule(
            product_id=product_id,
            workspace_id=product.workspace_id,
            name=request.name,
            description=request.description,
            rule_type=request.rule_type,
            severity=request.severity,
            configuration=request.configuration,
            compliance_tags=request.compliance_tags,
            business_owner=request.business_owner,
            technical_owner=request.technical_owner,
            created_by=get_user_id(current_user),
            updated_by=get_user_id(current_user),
        )

        db.add(rule)
        db.flush()  # Get the ID

        # Create audit log
        audit_log = DataQualityRuleAudit(
            rule_id=rule.id,
            action=AuditAction.CREATE,
            changed_by=get_user_id(current_user),
            new_values=rule.__dict__.copy(),
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )

        db.add(audit_log)
        db.commit()

        return DataQualityRuleResponse.model_validate(rule)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create rule: {str(e)}")


@router.get("/rules", response_model=List[DataQualityRuleResponse])
async def list_data_quality_rules(
    http_request: Request,
    product_id: Optional[UUID] = Query(None),
    workspace_id: Optional[UUID] = Query(None),
    rule_type: Optional[str] = Query(None),
    severity: Optional[RuleSeverity] = Query(None),
    status: Optional[RuleStatus] = Query(None),
    compliance_framework: Optional[str] = Query(None),
    include_deprecated: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List data quality rules with enterprise filtering and pagination."""
    try:
        # Build query with access control
        query = db.query(DataQualityRule)

        # Apply workspace access control
        if workspace_id:
            ensure_workspace_access(db, http_request, workspace_id)
            query = query.filter(DataQualityRule.workspace_id == workspace_id)
        elif product_id:
            ensure_product_access(db, http_request, product_id)
            query = query.filter(DataQualityRule.product_id == product_id)
        else:
            # Get accessible workspaces
            from ..core.scope import allowed_workspaces

            allowed_workspace_ids = allowed_workspaces(http_request, db)
            query = query.filter(DataQualityRule.workspace_id.in_(allowed_workspace_ids))

        # Apply filters
        if rule_type:
            query = query.filter(DataQualityRule.rule_type == rule_type)
        if severity:
            query = query.filter(DataQualityRule.severity == severity)
        if status:
            query = query.filter(DataQualityRule.status == status)
        if compliance_framework:
            query = query.filter(DataQualityRule.compliance_tags.contains([compliance_framework]))

        # Handle deprecated rules
        if not include_deprecated:
            query = query.filter(DataQualityRule.status != RuleStatus.DEPRECATED)

        # Apply pagination and ordering
        rules = query.order_by(desc(DataQualityRule.created_at)).offset(offset).limit(limit).all()

        return [DataQualityRuleResponse.model_validate(rule) for rule in rules]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rules: {str(e)}")


@router.put("/rules/{rule_id}", response_model=DataQualityRuleResponse)
async def update_data_quality_rule(
    rule_id: UUID,
    request: DataQualityRuleUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a data quality rule with audit trail."""
    try:
        # Get existing rule
        rule = db.query(DataQualityRule).filter(DataQualityRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        # Verify access
        ensure_product_access(db, http_request, rule.product_id)

        # Store old values for audit
        old_values = {
            "name": rule.name,
            "description": rule.description,
            "severity": rule.severity,
            "configuration": rule.configuration,
            "compliance_tags": rule.compliance_tags,
            "business_owner": rule.business_owner,
            "technical_owner": rule.technical_owner,
        }

        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if field != "change_reason" and hasattr(rule, field):
                setattr(rule, field, value)

        rule.updated_by = get_user_id(current_user)
        rule.updated_at = datetime.utcnow()

        # Create new version if significant changes
        if any(field in update_data for field in ["configuration", "severity", "rule_type"]):
            # Create new version
            new_rule = DataQualityRule(
                product_id=rule.product_id,
                workspace_id=rule.workspace_id,
                name=rule.name,
                description=rule.description,
                rule_type=rule.rule_type,
                severity=rule.severity,
                configuration=rule.configuration,
                compliance_tags=rule.compliance_tags,
                business_owner=rule.business_owner,
                technical_owner=rule.technical_owner,
                version=rule.version + 1,
                parent_rule_id=rule.id,
                created_by=current_user.get("sub"),
                updated_by=current_user.get("sub"),
            )

            # Mark old rule as not current
            rule.is_current = False

            db.add(new_rule)
            db.flush()

            # Create audit log for new version
            audit_log = DataQualityRuleAudit(
                rule_id=new_rule.id,
                action=AuditAction.UPDATE,
                changed_by=get_user_id(current_user),
                old_values=old_values,
                new_values=new_rule.__dict__.copy(),
                change_reason=request.change_reason,
                ip_address=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent"),
            )

            db.add(audit_log)
            rule = new_rule
        else:
            # Create audit log for simple update
            audit_log = DataQualityRuleAudit(
                rule_id=rule.id,
                action=AuditAction.UPDATE,
                changed_by=get_user_id(current_user),
                old_values=old_values,
                new_values=rule.__dict__.copy(),
                change_reason=request.change_reason,
                ip_address=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent"),
            )

            db.add(audit_log)

        db.commit()

        return DataQualityRuleResponse.model_validate(rule)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update rule: {str(e)}")


@router.get("/rules/{rule_id}/audit", response_model=List[DataQualityRuleAuditResponse])
async def get_rule_audit_trail(
    rule_id: UUID,
    http_request: Request,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get complete audit trail for a data quality rule."""
    try:
        # Verify rule exists and user has access
        rule = db.query(DataQualityRule).filter(DataQualityRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        ensure_product_access(db, http_request, rule.product_id)

        # Get audit logs
        audit_logs = (
            db.query(DataQualityRuleAudit)
            .filter(DataQualityRuleAudit.rule_id == rule_id)
            .order_by(desc(DataQualityRuleAudit.changed_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [DataQualityRuleAuditResponse.model_validate(log) for log in audit_logs]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit trail: {str(e)}")


@router.post("/compliance/reports", response_model=Dict[str, Any])
async def generate_compliance_report(
    request: ComplianceReportRequest,
    workspace_id: UUID,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate enterprise compliance reports."""
    try:
        # Verify workspace access
        ensure_workspace_access(db, http_request, workspace_id)

        # Build report data
        report_data = {
            "report_metadata": {
                "name": request.report_name,
                "type": request.report_type,
                "framework": request.compliance_framework,
                "period": {"start": request.period_start.isoformat(), "end": request.period_end.isoformat()},
                "generated_by": str(get_user_id(current_user)),
                "generated_at": datetime.utcnow().isoformat(),
            }
        }

        # Get rules in scope
        rules_query = (
            db.query(DataQualityRule)
            .filter(DataQualityRule.workspace_id == workspace_id)
            .filter(DataQualityRule.created_at >= request.period_start)
            .filter(DataQualityRule.created_at <= request.period_end)
        )

        if request.compliance_framework:
            rules_query = rules_query.filter(DataQualityRule.compliance_tags.contains([request.compliance_framework]))

        rules = rules_query.all()

        # Generate report sections
        if request.include_audit_trail:
            report_data["audit_trail"] = {"total_changes": len(rules), "changes_by_type": {}, "changes_by_user": {}}

        if request.include_violations:
            # Get violations for the period
            violations_query = (
                db.query(DqViolation)
                .join(DataQualityRule)
                .filter(DataQualityRule.workspace_id == workspace_id)
                .filter(DqViolation.created_at >= request.period_start)
                .filter(DqViolation.created_at <= request.period_end)
            )

            violations = violations_query.all()
            report_data["violations"] = {
                "total_violations": len(violations),
                "violations_by_severity": {},
                "violations_by_rule_type": {},
            }

        if request.include_metrics:
            # Calculate compliance metrics
            total_rules = len(rules)
            active_rules = len([r for r in rules if r.status == RuleStatus.ACTIVE])
            compliance_score = (active_rules / total_rules * 100) if total_rules > 0 else 0

            report_data["metrics"] = {
                "total_rules": total_rules,
                "active_rules": active_rules,
                "compliance_score": compliance_score,
                "rules_by_severity": {},
                "rules_by_type": {},
            }

        # Save report data to S3
        from primedata.services.s3_content_storage import (
            get_compliance_report_data_path,
            save_text_to_s3,
        )
        from primedata.storage.minio_client import MinIOClient
        import json
        
        # Create report first to get ID
        report = DataQualityComplianceReport(
            workspace_id=workspace_id,
            report_name=request.report_name,
            report_type=request.report_type,
            compliance_framework=request.compliance_framework,
            period_start=request.period_start,
            period_end=request.period_end,
            report_data=None,  # Will store small summary only
            report_data_path="",  # Temporary, will be set after saving to S3
            generated_by=get_user_id(current_user),
        )

        db.add(report)
        db.flush()  # Flush to get the ID
        
        # Save full report data to S3
        report_data_path = get_compliance_report_data_path(workspace_id, report.id)
        minio_client = MinIOClient()
        if not minio_client.put_json("primedata-exports", report_data_path, report_data):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save report data to storage"
            )
        
        # Update path
        report.report_data_path = report_data_path
        # Store small summary in DB
        report.report_data = {
            "report_name": report_data.get("report_metadata", {}).get("name"),
            "report_type": report_data.get("report_metadata", {}).get("type"),
            "total_rules": report_data.get("metrics", {}).get("total_rules", 0) if "metrics" in report_data else 0,
        }
        
        db.commit()

        return report_data

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.delete("/rules/{rule_id}")
async def delete_data_quality_rule(
    rule_id: UUID,
    http_request: Request,
    reason: str = Query(..., description="Reason for deletion"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Soft delete a data quality rule with audit trail."""
    try:
        # Get rule
        rule = db.query(DataQualityRule).filter(DataQualityRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        # Verify access
        ensure_product_access(db, http_request, rule.product_id)

        # Soft delete (mark as archived)
        rule.status = RuleStatus.ARCHIVED
        rule.updated_by = get_user_id(current_user)
        rule.updated_at = datetime.utcnow()

        # Create audit log
        audit_log = DataQualityRuleAudit(
            rule_id=rule.id,
            action=AuditAction.DELETE,
            changed_by=get_user_id(current_user),
            change_reason=reason,
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )

        db.add(audit_log)
        db.commit()

        return {"message": "Rule deleted successfully", "rule_id": str(rule_id)}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {str(e)}")
