from enum import StrEnum


class RoleCode(StrEnum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    SUPPLY_COORDINATOR = "SUPPLY_COORDINATOR"
    WAREHOUSE_OPERATOR = "WAREHOUSE_OPERATOR"
    AUDITOR = "AUDITOR"
    FARMER = "FARMER"
    BUYER = "BUYER"


class PermissionCode(StrEnum):
    REQUIREMENT_VIEW = "requirement.view"
    REQUIREMENT_CREATE = "requirement.create"
    REQUIREMENT_UPDATE = "requirement.update"
    SUPPLY_VIEW = "supply.view"
    SUPPLY_MANAGE = "supply.manage"
    RECOVERY_VIEW = "recovery.view"
    RECOVERY_PROPOSE = "recovery.propose"
    RECOVERY_APPROVE = "recovery.approve"
    RECOVERY_APPROVE_ELEVATED = "recovery.approve_elevated"
    # Held by no user role: only the recovery gateway executes, and only an approved proposal (agents/application/gateway.py).
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
    FARMER_SUPPLY_REPORT = "farmer_supply.report"
    MARKETPLACE_VIEW = "marketplace.view"
    ORDER_VIEW = "order.view"
    ORDER_CREATE = "order.create"
    AVAILABILITY_ALERT_MANAGE = "availability_alert.manage"
    # R1 WP4 (fulfilment and reconciliation; P5, P6, P11)
    FULFILMENT_SITE_MANAGE = "fulfilment_site.manage"
    TRADE_RECONCILE = "trade.reconcile"              # reconciliation versions, correction reviews, dispute resolution
    TRADE_ACCEPT_VARIANCE = "trade.accept_variance"  # close an order with an accepted, documented variance
    BUYER_CONFIRMATION_RELAY = "buyer_confirmation.relay"  # record a buyer's confirmation given through another channel
    DELIVERY_CONFIRM_OWN = "delivery.confirm_own"    # a buyer confirms or disputes their own deliveries
    DISPUTE_RAISE = "dispute.raise"                  # operational staff raise a discrepancy
    AUDIT_FLAG = "audit.flag"                        # auditors flag an issue without changing anything


# Recovery role policy (R1 WP3, product-owner decision 2):
# * the recovery agent proposes; supply coordinators and above approve ordinary recovery within existing supplier
#   consent, buyer terms and approved cost tolerances (RECOVERY_APPROVE);
# * a proposal above the organization's cost tolerance, with unknown cost, or with no tolerance set and any cost
#   increase also needs a second, different approver with RECOVERY_APPROVE_ELEVATED (procurement manager or
#   organization administrator);
# * execution is never a user privilege: RECOVERY_EXECUTE is held by no role, platform administrators included.
#   The gateway executes an approved proposal after re-verifying the approvals (agents/application/gateway.py).
# Fulfilment and reconciliation (R1 WP4, P11): warehouse operators record physical facts but cannot certify
# commercial reconciliation; coordinators and procurement managers reconcile; procurement managers and organization
# administrators accept variances; buyers confirm or dispute only their own deliveries; auditors only flag.
P = PermissionCode
ROLE_PERMISSIONS: dict[RoleCode, frozenset[PermissionCode]] = {
    RoleCode.PLATFORM_ADMIN: frozenset(PermissionCode) - {P.RECOVERY_EXECUTE},
    RoleCode.ORGANIZATION_ADMIN: frozenset({
        P.REQUIREMENT_VIEW, P.SUPPLY_VIEW, P.RECOVERY_VIEW, P.RECOVERY_APPROVE, P.RECOVERY_APPROVE_ELEVATED,
        P.RECEIVING_VIEW, P.TRADE_EVIDENCE_VIEW, P.COMPLIANCE_VIEW, P.USER_VIEW, P.USER_INVITE, P.USER_MANAGE_ROLE,
        P.AUDIT_VIEW, P.APPROVAL_POLICY_VIEW, P.APPROVAL_POLICY_MANAGE,
        P.TRADE_ACCEPT_VARIANCE, P.FULFILMENT_SITE_MANAGE, P.AUDIT_FLAG,
    }),
    RoleCode.PROCUREMENT_MANAGER: frozenset({
        P.REQUIREMENT_VIEW, P.REQUIREMENT_CREATE, P.REQUIREMENT_UPDATE, P.SUPPLY_VIEW, P.RECOVERY_VIEW,
        P.RECOVERY_PROPOSE, P.RECOVERY_APPROVE, P.RECOVERY_APPROVE_ELEVATED, P.TRADE_EVIDENCE_VIEW, P.COMPLIANCE_VIEW,
        P.AUDIT_VIEW, P.APPROVAL_POLICY_VIEW,
        P.RECEIVING_VIEW, P.TRADE_RECONCILE, P.TRADE_ACCEPT_VARIANCE, P.BUYER_CONFIRMATION_RELAY, P.DISPUTE_RAISE,
    }),
    # Spec R1 §2: the coordinator/exporter manages orders as well as supply.
    RoleCode.SUPPLY_COORDINATOR: frozenset({
        P.REQUIREMENT_VIEW, P.REQUIREMENT_CREATE, P.REQUIREMENT_UPDATE, P.SUPPLY_VIEW, P.SUPPLY_MANAGE,
        P.RECOVERY_VIEW, P.RECOVERY_PROPOSE, P.RECOVERY_APPROVE, P.RECEIVING_VIEW, P.COMPLIANCE_VIEW, P.AUDIT_VIEW,
        P.FULFILMENT_SITE_MANAGE, P.TRADE_RECONCILE, P.BUYER_CONFIRMATION_RELAY, P.DISPUTE_RAISE,
    }),
    RoleCode.WAREHOUSE_OPERATOR: frozenset({
        P.REQUIREMENT_VIEW, P.SUPPLY_VIEW, P.RECEIVING_VIEW, P.RECEIVING_RECORD, P.GRADING_RECORD,
        P.SHIPMENT_CREATE, P.SHIPMENT_DISPATCH, P.DELIVERY_CONFIRM, P.DISPUTE_RAISE,
    }),
    RoleCode.AUDITOR: frozenset({
        P.REQUIREMENT_VIEW, P.SUPPLY_VIEW, P.RECOVERY_VIEW, P.RECEIVING_VIEW, P.TRADE_EVIDENCE_VIEW,
        P.COMPLIANCE_VIEW, P.USER_VIEW, P.AUDIT_VIEW, P.APPROVAL_POLICY_VIEW, P.AUDIT_FLAG,
    }),
    RoleCode.FARMER: frozenset({P.SUPPLY_VIEW, P.TRADE_EVIDENCE_VIEW, P.FARMER_SUPPLY_REPORT}),
    RoleCode.BUYER: frozenset({
        P.MARKETPLACE_VIEW, P.ORDER_VIEW, P.ORDER_CREATE, P.AVAILABILITY_ALERT_MANAGE, P.DELIVERY_CONFIRM_OWN,
    }),
}
