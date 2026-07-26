"""
Tools package
=============
Importing this package registers every tool with agent.registry.

HOW TO ADD A NEW TOOL:
1. Create tools/your_tool.py
2. Decorate each capability with @action("your_tool_name", "action_name", ...)
   (see any existing tool file for the pattern, e.g. tools/browser_tool.py)
3. Import your new module below.

That's it - no changes needed in the executor or planner, they read the
registry automatically.
"""

from . import whatsapp_tool  # noqa: F401
from . import system_tool  # noqa: F401
from . import window_tool  # noqa: F401
from . import vscode_tool  # noqa: F401
from . import screenshot_tool  # noqa: F401
from . import camera_tool  # noqa: F401
from . import bluetooth_tool  # noqa: F401
from . import file_tool  # noqa: F401
from . import browser_tool  # noqa: F401
from . import clipboard_tool  # noqa: F401
from . import volume_tool  # noqa: F401
from . import youtube_tool  # noqa: F401
from . import instagram_tool  # noqa: F401
from . import wifi_tool  # noqa: F401
from . import notepad_tool  # noqa: F401
from . import alarm_tool  # noqa: F401
from . import notes_tool  # noqa: F401
from . import search_tool  # noqa: F401
from . import coding_tool  # noqa: F401
from . import email_tool  # noqa: F401
