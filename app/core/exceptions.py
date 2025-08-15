class BrowserAutomationError(Exception):
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details if details is not None else {}
        super().__init__(self.message)

    def to_dict(self):
        return {"message": self.message, "details": self.details}

class SessionNotFoundError(BrowserAutomationError):
    def __init__(self, session_id: str):
        super().__init__(f"Session with ID '{session_id}' not found.", {"session_id": session_id})

class NavigationError(BrowserAutomationError):
    def __init__(self, url: str, message: str = "Navigation failed.", details: dict = None):
        super().__init__(f"Navigation to {url} failed: {message}", {"url": url, **(details if details is not None else {})})

class ElementError(BrowserAutomationError):
    def __init__(self, selector: str, message: str = "Element operation failed.", details: dict = None):
        super().__init__(f"Element '{selector}' operation failed: {message}", {"selector": selector, **(details if details is not None else {})})

class InvalidURLError(BrowserAutomationError):
    def __init__(self, url: str):
        super().__init__(f"Invalid URL provided: {url}", {"url": url})

class ElementNotFoundError(ElementError):
    def __init__(self, selector: str):
        super().__init__(selector, f"Element '{selector}' not found.")

class ElementNotInteractableError(ElementError):
    def __init__(self, selector: str):
        super().__init__(selector, f"Element '{selector}' is not interactable.")

class InvalidSelectorError(ElementError):
    def __init__(self, selector: str):
        super().__init__(selector, f"Invalid selector provided: {selector}")

class MCPError(BrowserAutomationError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)

class ToolNotFoundError(MCPError):
    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' not found.", {"tool_name": tool_name})

class InvalidToolArgumentsError(MCPError):
    def __init__(self, tool_name: str, missing_args: list = None, invalid_args: dict = None):
        message = f"Invalid arguments for tool '{tool_name}'."
        details = {"tool_name": tool_name}
        if missing_args:
            message += f" Missing: {', '.join(missing_args)}."
            details["missing_arguments"] = missing_args
        if invalid_args:
            message += f" Invalid: {invalid_args}."
            details["invalid_arguments"] = invalid_args
        super().__init__(message, details)


