"""
Minimal stand-in for the ``albert`` module, which only exists inside Albert.

Implements just what the extension uses. Icons are plain tuples describing how they were built and
calls with side effects are recorded, so tests can assert on them.
"""

detached_processes = []
debug_messages = []


def reset():
    detached_processes.clear()
    debug_messages.clear()


def debug(msg):
    debug_messages.append(msg)


def runDetachedProcess(cmdln, workdir=""):
    detached_processes.append(list(cmdln))
    return 1


class Color:
    def __init__(self, r, g, b, a=255):
        self.r, self.g, self.b, self.a = r, g, b, a


class Brush:
    def __init__(self, color):
        self.color = color


class Icon:
    @staticmethod
    def theme(name):
        return ("theme", name)

    @staticmethod
    def iconified(icon, background_brush=None, border_radius=None, border_width=None,
                  border_brush=None):
        return ("iconified", icon, background_brush)


class Action:
    def __init__(self, id, text, callable):
        self.id = id
        self.text = text
        self.callable = callable


class Item:
    def __init__(self):
        pass


class IndexItem:
    def __init__(self, item, string):
        self.item = item
        self.string = string


class PluginInstance:
    def __init__(self):
        pass


class IndexQueryHandler:
    def __init__(self):
        self.index_items = None

    def setIndexItems(self, index_items):
        self.index_items = index_items
