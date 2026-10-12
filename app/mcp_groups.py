"""Stable service labels without changing public tool identifiers."""

SERVICE_META = "de.theinloth.icloud/service"
SERVICES = ("calendar", "mail", "contacts", "drive", "reminders")
TITLES = {"calendar": "Calendar", "mail": "Mail", "contacts": "Contacts", "drive": "Drive", "reminders": "Reminders"}


def service_for_tool(name):
    if "drive" in name:
        return "drive"
    if "reminder" in name:
        return "reminders"
    if "contact" in name or name == "list_addressbooks":
        return "contacts"
    if "email" in name or "mailbox" in name or name in {"create_draft", "update_draft"}:
        return "mail"
    if "calendar" in name or "event" in name:
        return "calendar"
    return None


def grouped_tools(tools):
    result = []
    for tool in tools:
        service = service_for_tool(tool.name)
        if service is not None:
            title = tool.title or tool.name.replace("_", " ").capitalize()
            prefix = TITLES[service] + " · "
            tool = tool.model_copy(update={
                "title": title if title.startswith(prefix) else prefix + title,
                "meta": {**(tool.meta or {}), SERVICE_META: service},
            })
        result.append(tool)
    return sorted(result, key=lambda tool: (
        SERVICES.index(service_for_tool(tool.name)) if service_for_tool(tool.name) in SERVICES else len(SERVICES),
        tool.name,
    ))
