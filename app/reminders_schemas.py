"""Public structured-content contracts; native MCP content is passed through unchanged.

Optional structural fields permit the published 1.1.0 backend. Unknown fields
remain allowed so a newer backend can add metadata without hiding a confirmed write.
"""

from typing import Annotated, Literal

from mcp_types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, TypeAdapter

from app.reminders import _PUBLIC_ERRORS


WriteStatus = Literal["not_sent", "failed", "succeeded", "unknown"]
RetryClass = Literal["retryable_safe", "retryable_after_read", "not_retryable"]
StructureField = Literal["ReminderIDs", "ReminderIDsAsset", "MembershipsOfRemindersInSectionsAsData", "SectionIDsOrderingAsData", "ResolutionTokenMap"]
StructureReason = Literal["too_large", "invalid_json", "invalid_version", "unsupported_version", "missing_entries", "invalid_entries", "metadata_unavailable"]


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class StructureWarning(ResponseModel):
    error_code: Literal["unsupported_structure"]
    list_id: str
    record_type: str
    structure_field: StructureField
    structure_reason: StructureReason
    structure_version: int | None = None


class ReminderError(ResponseModel):
    error_code: str = Field(description="Application-owned error code; never raw upstream exception text.",
                            json_schema_extra={"enum": sorted(_PUBLIC_ERRORS)})
    retry_class: RetryClass
    retryable: bool
    operation: str | None = None
    request_id: str | None = None
    write_status: WriteStatus | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    upstream_status: int | None = Field(default=None, ge=100, le=599)
    upstream_error_code: str | None = None
    list_id: str | None = None
    record_type: str | None = None
    structure_field: StructureField | None = None
    structure_reason: StructureReason | None = None
    structure_version: int | None = None


class WithWarnings(ResponseModel):
    structure_warnings: list[StructureWarning] | None = None


class Reminder(ResponseModel):
    id: str
    title: str
    completed: bool
    priority: int = Field(description="0=none, 9=low, 5=medium, 1=high; independent of manual order.")
    list_name: str
    list_ref: str | None = None
    completion_date: str | None = None
    due: str | None = None
    notes: str | None = None
    parent_ref: str | None = None
    modified_ts: int | None = None
    assignee_id: str | None = None
    section_ref: str | None = None
    section_name: str | None = None
    sort_index: int | None = Field(default=None, ge=-1, description="Native list position; -1 when unavailable, gaps after filtering are normal.")
    depth: int | None = Field(default=None, ge=0)


class ReminderTree(ResponseModel):
    reminder: Reminder
    subtasks: list["ReminderTree"]


class ReminderList(ResponseModel):
    id: str
    name: str


class ListsResult(WithWarnings):
    lists: list[ReminderList]


class ReminderResult(WithWarnings):
    reminder: Reminder


class ReminderPage(WithWarnings):
    reminders: list[Reminder]
    total: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)
    tree: list[ReminderTree] | None = None
    legend: dict[str, str] | None = None


class SyncResult(WithWarnings):
    reminders: int = Field(ge=0)
    lists: int = Field(ge=0)


class Participant(ResponseModel):
    id: str
    role: str
    permission: str
    is_current_user: bool
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class ParticipantsResult(ResponseModel):
    list_id: str
    shared: bool
    participants: list[Participant]


class Section(ResponseModel):
    id: str
    title: str
    list_id: str
    sort_index: int | None = Field(default=None, ge=0)


class SectionsResult(WithWarnings):
    list_id: str
    sections: list[Section]


class MutationResult(ResponseModel):
    id: str
    write_status: Literal["succeeded"] | None = Field(default=None, description="Present on the combined backend; absent on older backends.")


class CreateResult(MutationResult):
    status: Literal["created", "already_created"]


class UpdateResult(MutationResult):
    status: Literal["updated"]


class CompleteResult(MutationResult):
    status: Literal["completed"]


class DeleteResult(MutationResult):
    status: Literal["deleted"]


class AssignmentResult(MutationResult):
    status: Literal["assigned", "unassigned", "unchanged"]


class CreateSectionResult(MutationResult):
    status: Literal["created"]


class MoveResult(MutationResult):
    status: Literal["moved"]


class ReorderResult(MutationResult):
    status: Literal["reordered", "unchanged"]


class BatchNativeResult(CallToolResult):
    # The invoked tool publishes its payload schema. Preserve the native JSON
    # here even if an older/newer backend differs: partial results must survive.
    structured_content: dict[str, JsonValue]
    is_error: Literal[False] = False


class BatchStep(ResponseModel):
    tool: Literal["create_reminder_section", "create_reminder", "update_reminder", "move_reminder", "reorder_reminders"]
    target: str = Field(description="Target path in the submitted structure.")
    result: BatchNativeResult | None = Field(default=None, description="Confirmed native MCP result; omitted in previews and for the failed step.")


class BatchError(ReminderError):
    code: str
    message: str


class BatchResult(ResponseModel):
    list_id: str
    status: Literal["preview", "applied", "failed"]
    dry_run: bool
    atomic: Literal[False]
    planned_operations: int = Field(ge=0)
    completed_operations: int = Field(ge=0)
    operations: list[BatchStep]
    ids: dict[str, str] = Field(description="Target paths mapped to existing or confirmed newly created IDs.")
    error: BatchError | None = None
    failed_operation: BatchStep | None = None
    write_result_unknown: bool | None = None
    inspect_before_retry: bool | None = None


# RootModel keeps the wire object unchanged; object is required by MCP's outputSchema.
class ListsResponse(RootModel[ListsResult | ReminderError]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


def _response_model(name: str, success: type[BaseModel]):
    return type(name, (RootModel[success | ReminderError],), {
        "__module__": __name__, "model_config": ConfigDict(json_schema_extra={"type": "object"}),
    })


PageResponse = _response_model("PageResponse", ReminderPage)
GetResponse = _response_model("GetResponse", ReminderResult)
CreateResponse = _response_model("CreateResponse", CreateResult)
UpdateResponse = _response_model("UpdateResponse", UpdateResult)
CompleteResponse = _response_model("CompleteResponse", CompleteResult)
DeleteResponse = _response_model("DeleteResponse", DeleteResult)
SyncResponse = _response_model("SyncResponse", SyncResult)
ParticipantsResponse = _response_model("ParticipantsResponse", ParticipantsResult)
AssignmentResponse = _response_model("AssignmentResponse", AssignmentResult)
SectionsResponse = _response_model("SectionsResponse", SectionsResult)
CreateSectionResponse = _response_model("CreateSectionResponse", CreateSectionResult)
MoveResponse = _response_model("MoveResponse", MoveResult)
ReorderResponse = _response_model("ReorderResponse", ReorderResult)
BatchResponse = _response_model("BatchResponse", BatchResult)

ListsReply = Annotated[CallToolResult, ListsResponse]
PageReply = Annotated[CallToolResult, PageResponse]
GetReply = Annotated[CallToolResult, GetResponse]
CreateReply = Annotated[CallToolResult, CreateResponse]
UpdateReply = Annotated[CallToolResult, UpdateResponse]
CompleteReply = Annotated[CallToolResult, CompleteResponse]
DeleteReply = Annotated[CallToolResult, DeleteResponse]
SyncReply = Annotated[CallToolResult, SyncResponse]
ParticipantsReply = Annotated[CallToolResult, ParticipantsResponse]
AssignmentReply = Annotated[CallToolResult, AssignmentResponse]
SectionsReply = Annotated[CallToolResult, SectionsResponse]
CreateSectionReply = Annotated[CallToolResult, CreateSectionResponse]
MoveReply = Annotated[CallToolResult, MoveResponse]
ReorderReply = Annotated[CallToolResult, ReorderResponse]
BatchReply = Annotated[CallToolResult, BatchResponse]

RESPONSES = {
    "list_reminder_lists": ListsResponse, "list_reminders": PageResponse,
    "get_reminder": GetResponse, "create_reminder": CreateResponse,
    "update_reminder": UpdateResponse, "complete_reminder": CompleteResponse,
    "delete_reminder": DeleteResponse, "sync_reminders": SyncResponse,
    "list_reminder_participants": ParticipantsResponse, "assign_reminder": AssignmentResponse,
    "list_reminder_sections": SectionsResponse, "create_reminder_section": CreateSectionResponse,
    "move_reminder": MoveResponse, "reorder_reminders": ReorderResponse,
    "batch_update_reminders": BatchResponse,
}
VALIDATORS = {name: TypeAdapter(model) for name, model in RESPONSES.items()}
