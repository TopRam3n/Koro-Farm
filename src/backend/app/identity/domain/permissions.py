from enum import StrEnum


class RoleCode(StrEnum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    SUPPLY_COORDINATOR = "SUPPLY_COORDINATOR"
    WAREHOUSE_OPERATOR = "WAREHOUSE_OPERATOR"
    AUDITOR = "AUDITOR"
    FARMER = "FARMER"


class PermissionCode(StrEnum):
    REQUIREMENT_VIEW = "requirement.view"
    REQUIREMENT_CREATE = "requirement.create"
    REQUIREMENT_UPDATE = "requirement.update"
    SUPPLY_VIEW = "supply.view"
    SUPPLY_MANAGE = "supply.manage"
    RECOVERY_VIEW = "recovery.view"
    RECOVERY_PROPOSE = "recovery.propose"
    RECOVERY_APPROVE = "recovery.approve"
    RECOVERY_EXECUTE = "recovery.execute"
    RECEIVING_VIEW = "receiving.view"
    RECEIVING_RECORD = "receiving.record"
    GRADING_RECORD = "grading.record"
    SHIPMENT_CREATE = "shipment.create"
    SHIPMENT_DISPATCH = "shipment.dispatch"
    DELIVERY_CONFIRM = "delivery.confirm"
    TRADE_EVIDENCE_VIEW = "trade_evidence.view"
    COMPLIANCE_VIEW = "compliance.view"
    COMPLIANCE_MANAGE = "compliance.manage"
    USER_VIEW = "user.view"
    USER_INVITE = "user.invite"
    USER_MANAGE_ROLE = "user.manage_role"
    AUDIT_VIEW = "audit.view"
    APPROVAL_POLICY_VIEW = "approval_policy.view"
    APPROVAL_POLICY_MANAGE = "approval_policy.manage"
    AGENT_EVALUATION_VIEW = "agent_evaluation.view"
    AGENT_EVALUATION_RUN = "agent_evaluation.run"


ROLE_PERMISSIONS: dict[RoleCode, frozenset[PermissionCode]] = {
    RoleCode.PLATFORM_ADMIN: frozenset(PermissionCode),
    RoleCode.ORGANIZATION_ADMIN: frozenset({
        PermissionCode.REQUIREMENT_VIEW, PermissionCode.SUPPLY_VIEW, PermissionCode.RECOVERY_VIEW,
        PermissionCode.RECOVERY_APPROVE, PermissionCode.RECEIVING_VIEW, PermissionCode.TRADE_EVIDENCE_VIEW,
        PermissionCode.COMPLIANCE_VIEW, PermissionCode.USER_VIEW, PermissionCode.USER_INVITE,
        PermissionCode.USER_MANAGE_ROLE, PermissionCode.AUDIT_VIEW, PermissionCode.APPROVAL_POLICY_VIEW,
        PermissionCode.APPROVAL_POLICY_MANAGE,
    }),
    RoleCode.PROCUREMENT_MANAGER: frozenset({
        PermissionCode.REQUIREMENT_VIEW, PermissionCode.REQUIREMENT_CREATE, PermissionCode.REQUIREMENT_UPDATE,
        PermissionCode.SUPPLY_VIEW, PermissionCode.RECOVERY_VIEW, PermissionCode.RECOVERY_APPROVE,
        PermissionCode.TRADE_EVIDENCE_VIEW, PermissionCode.COMPLIANCE_VIEW, PermissionCode.AUDIT_VIEW,
        PermissionCode.APPROVAL_POLICY_VIEW,
    }),
    RoleCode.SUPPLY_COORDINATOR: frozenset({
        PermissionCode.REQUIREMENT_VIEW, PermissionCode.SUPPLY_VIEW, PermissionCode.SUPPLY_MANAGE,
        PermissionCode.RECOVERY_VIEW, PermissionCode.RECOVERY_PROPOSE, PermissionCode.RECOVERY_EXECUTE,
        PermissionCode.RECEIVING_VIEW, PermissionCode.COMPLIANCE_VIEW, PermissionCode.AUDIT_VIEW,
    }),
    RoleCode.WAREHOUSE_OPERATOR: frozenset({
        PermissionCode.REQUIREMENT_VIEW, PermissionCode.SUPPLY_VIEW, PermissionCode.RECEIVING_VIEW,
        PermissionCode.RECEIVING_RECORD, PermissionCode.GRADING_RECORD, PermissionCode.SHIPMENT_CREATE,
        PermissionCode.SHIPMENT_DISPATCH, PermissionCode.DELIVERY_CONFIRM,
    }),
    RoleCode.AUDITOR: frozenset({
        PermissionCode.REQUIREMENT_VIEW, PermissionCode.SUPPLY_VIEW, PermissionCode.RECOVERY_VIEW,
        PermissionCode.RECEIVING_VIEW, PermissionCode.TRADE_EVIDENCE_VIEW, PermissionCode.COMPLIANCE_VIEW,
        PermissionCode.USER_VIEW, PermissionCode.AUDIT_VIEW, PermissionCode.APPROVAL_POLICY_VIEW,
    }),
    RoleCode.FARMER: frozenset({PermissionCode.SUPPLY_VIEW, PermissionCode.TRADE_EVIDENCE_VIEW}),
}
