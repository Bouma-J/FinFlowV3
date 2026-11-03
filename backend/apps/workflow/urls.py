from rest_framework.routers import DefaultRouter

from .views import (
    ApprovalConditionViewSet,
    ApprovalStepViewSet,
    ApprovalTaskViewSet,
    WorkflowDefinitionViewSet,
    WorkflowInstanceViewSet,
)

router = DefaultRouter()
router.register("workflow-definitions", WorkflowDefinitionViewSet, basename="workflow-definition")
router.register("workflow-steps", ApprovalStepViewSet, basename="workflow-step")
router.register("workflow-instances", WorkflowInstanceViewSet, basename="workflow-instance")
router.register("approval-tasks", ApprovalTaskViewSet, basename="approval-task")
router.register("approval-conditions", ApprovalConditionViewSet, basename="approval-condition")

urlpatterns = router.urls
